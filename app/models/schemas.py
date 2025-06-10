from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict
from datetime import datetime

# Patient Schemas
class PatientBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    insurance_provider: Optional[str] = None
    policy_number: Optional[str] = None

class PatientCreate(PatientBase):
    pass

class PatientResponse(PatientBase):
    id: int
    created_at: datetime
    
    class Config:
        orm_mode = True

# Appointment Schemas
class AppointmentBase(BaseModel):
    doctor_name: str
    appointment_date: datetime
    reason: Optional[str] = None
    status: str = "scheduled"

class AppointmentCreate(AppointmentBase):
    patient_id: int

class AppointmentResponse(AppointmentBase):
    id: int
    patient_id: int
    confirmation_number: str
    created_at: datetime
    
    class Config:
        orm_mode = True

# Insurance Verification Schemas
class InsuranceVerificationRequest(BaseModel):
    patient_name: str
    date_of_birth: datetime
    insurance_provider: str
    policy_number: str
    procedure_code: Optional[str] = None
    service_description: Optional[str] = None

class InsuranceVerificationResponse(BaseModel):
    is_covered: bool
    coverage_percentage: Optional[float] = None
    deductible_remaining: Optional[float] = None
    copay_amount: Optional[float] = None
    authorization_required: bool = False
    notes: Optional[str] = None

# Voice Processing Schemas
class VoiceProcessRequest(BaseModel):
    session_id: Optional[str] = None

class VoiceProcessResponse(BaseModel):
    session_id: str
    transcription: str
    response_text: str
    response_audio_url: str
    intent: Optional[str] = None

# Conversation Schemas
class Message(BaseModel):
    role: str
    content: str

class ConversationState(BaseModel):
    session_id: str
    messages: List[Message]
    intent: Optional[str] = None
    collected_data: Dict = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

# Clinic Info Schemas
class ClinicInfoResponse(BaseModel):
    name: str
    address: str
    phone: str
    email: str
    hours: Dict[str, str]
    services: List[str]
    doctors: List[Dict[str, str]]
    faqs: List[Dict[str, str]]