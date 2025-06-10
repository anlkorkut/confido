import os
import uuid
import tempfile
from typing import Dict, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.schemas import (
    PatientCreate, PatientResponse, 
    AppointmentCreate, AppointmentResponse,
    InsuranceVerificationRequest, InsuranceVerificationResponse,
    VoiceProcessRequest, VoiceProcessResponse
)
from app.services.openai_wrapper import OpenAIWrapper
from app.services.voice_processor import VoiceProcessor
from app.services.conversation_manager import ConversationManager
from app.services.healthcare_service import HealthcareService
from app.utils.audio_utils import save_audio_file, validate_audio_file
from app.utils.logger import get_logger, log_request, log_response
from app.config import settings

# Create router
router = APIRouter()

# Initialize logger
logger = get_logger(__name__)

# Dependency to get service instances
def get_services(db: Session = Depends(get_db)):
    openai_wrapper = OpenAIWrapper(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=settings.openai_temperature
    )
    
    voice_processor = VoiceProcessor(
        whisper_api_key=settings.openai_api_key,
        gcp_credentials_path=settings.google_cloud_credentials_path
    )
    
    healthcare_service = HealthcareService(db_session=db)
    
    conversation_manager = ConversationManager(
        openai_wrapper=openai_wrapper,
        healthcare_service=healthcare_service
    )
    
    return {
        "openai_wrapper": openai_wrapper,
        "voice_processor": voice_processor,
        "healthcare_service": healthcare_service,
        "conversation_manager": conversation_manager
    }

# Voice processing endpoint
@router.post("/api/v1/voice/process", response_model=VoiceProcessResponse)
async def process_voice_interaction(
    audio_file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    services: Dict = Depends(get_services),
    db: Session = Depends(get_db)
):
    try:
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        logger.info("Processing voice interaction for session %s", session_id)
        
        # Save uploaded file
        temp_file_path = None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(await audio_file.read())
        
        # Validate audio file
        if not validate_audio_file(temp_file_path):
            os.remove(temp_file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid audio file. Please upload a valid audio file (WAV, MP3, OGG) between 0.5s and 5 minutes."
            )
        
        # Transcribe audio to text
        transcription = await services["voice_processor"].transcribe_audio(temp_file_path)
        logger.info("Transcription: %s", transcription)
        
        # Clean up temporary file
        os.remove(temp_file_path)
        
        # Process conversation
        response_text = await services["conversation_manager"].process_conversation_turn(
            session_id=session_id,
            user_input=transcription
        )
        
        # Convert response to speech
        voice_config = {
            "language_code": settings.tts_language_code,
            "name": settings.tts_voice_name,
            "speaking_rate": 1.0,
            "pitch": 0.0
        }
        
        audio_content = await services["voice_processor"].synthesize_speech(
            text=response_text,
            voice_config=voice_config
        )
        
        # Save audio response to a temporary file
        response_file_path = save_audio_file(audio_content, "mp3")
        
        # Determine intent (for response metadata)
        intent = services["conversation_manager"].conversation_states.get(session_id, {}).get("intent", "unknown")
        
        return VoiceProcessResponse(
            session_id=session_id,
            transcription=transcription,
            response_text=response_text,
            response_audio_url=f"/api/v1/audio/{os.path.basename(response_file_path)}",
            intent=intent
        )
        
    except Exception as e:
        logger.error("Error processing voice interaction: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing voice interaction: {str(e)}"
        )

# Serve generated audio files
@router.get("/api/v1/audio/{filename}")
async def get_audio_file(filename: str):
    file_path = os.path.join(tempfile.gettempdir(), filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found"
        )
    return FileResponse(file_path, media_type="audio/mpeg")

# Appointment booking endpoint
@router.post("/api/v1/appointments/book", response_model=AppointmentResponse)
async def book_appointment(
    appointment_data: AppointmentCreate,
    services: Dict = Depends(get_services),
    db: Session = Depends(get_db)
):
    try:
        # Get patient info
        patient = db.query(Patient).filter(Patient.id == appointment_data.patient_id).first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with ID {appointment_data.patient_id} not found"
            )
        
        # Book appointment
        result = await services["healthcare_service"].book_appointment(
            patient_info={
                "name": patient.name,
                "email": patient.email,
                "phone": patient.phone
            },
            appointment_details={
                "doctor": appointment_data.doctor_name,
                "date": appointment_data.appointment_date.strftime("%Y-%m-%d"),
                "time": appointment_data.appointment_date.strftime("%H:%M"),
                "reason": appointment_data.reason
            }
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to book appointment")
            )
        
        # Return appointment details
        return AppointmentResponse(
            id=result["appointment_id"],
            patient_id=appointment_data.patient_id,
            doctor_name=appointment_data.doctor_name,
            appointment_date=appointment_data.appointment_date,
            reason=appointment_data.reason,
            status="scheduled",
            confirmation_number=result["confirmation_number"],
            created_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error booking appointment: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error booking appointment: {str(e)}"
        )

# Insurance verification endpoint
@router.post("/api/v1/insurance/verify", response_model=InsuranceVerificationResponse)
async def verify_insurance(
    insurance_data: InsuranceVerificationRequest,
    services: Dict = Depends(get_services),
    db: Session = Depends(get_db)
):
    try:
        result = await services["healthcare_service"].verify_insurance(
            patient_info={
                "name": insurance_data.patient_name,
                "date_of_birth": insurance_data.date_of_birth
            },
            insurance_details={
                "provider": insurance_data.insurance_provider,
                "policy_number": insurance_data.policy_number,
                "procedure": insurance_data.procedure_code or insurance_data.service_description
            }
        )
        
        return InsuranceVerificationResponse(
            is_covered=result["is_covered"],
            coverage_percentage=result.get("coverage_percentage"),
            deductible_remaining=result.get("deductible_remaining"),
            copay_amount=result.get("copay_amount"),
            authorization_required=result.get("authorization_required", False),
            notes=result.get("notes")
        )
        
    except Exception as e:
        logger.error("Error verifying insurance: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying insurance: {str(e)}"
        )

# Clinic information endpoint
@router.get("/api/v1/clinic/info")
async def get_clinic_info(
    query_type: Optional[str] = None,
    services: Dict = Depends(get_services)
):
    try:
        return await services["healthcare_service"].get_clinic_info(query_type or "general")
    except Exception as e:
        logger.error("Error getting clinic info: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting clinic information: {str(e)}"
        )

# WebSocket endpoint for real-time voice interaction
@router.websocket("/ws/voice")
async def websocket_voice_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    await websocket.accept()
    
    # Initialize services
    services = get_services(db)
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    logger.info("WebSocket connection established for session %s", session_id)
    
    try:
        while True:
            # Receive audio data
            data = await websocket.receive_bytes()
            
            # Save audio data to temporary file
            temp_file_path = save_audio_file(data, "wav")
            
            # Process audio
            if validate_audio_file(temp_file_path):
                # Transcribe audio
                transcription = await services["voice_processor"].transcribe_audio(temp_file_path)
                
                # Process conversation
                response_text = await services["conversation_manager"].process_conversation_turn(
                    session_id=session_id,
                    user_input=transcription
                )
                
                # Convert response to speech
                voice_config = {
                    "language_code": settings.tts_language_code,
                    "name": settings.tts_voice_name,
                    "speaking_rate": 1.0,
                    "pitch": 0.0
                }
                
                audio_content = await services["voice_processor"].synthesize_speech(
                    text=response_text,
                    voice_config=voice_config
                )
                
                # Send response
                await websocket.send_json({
                    "transcription": transcription,
                    "response": response_text
                })
                
                # Send audio response
                await websocket.send_bytes(audio_content)
            
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception as e:
        logger.error("Error in WebSocket connection: %s", str(e))
        await websocket.close()

# Import necessary modules
from datetime import datetime
from app.models.database import Patient