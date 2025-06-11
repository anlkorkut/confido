"""
Dependencies for the FastAPI application.
This module provides singleton instances of services used throughout the application.
"""
import logging
import random
import string
from app.services.conversation_manager import ConversationManager
from app.services.openai_wrapper import OpenAIWrapper
from app.services.voice_processor import VoiceProcessor
from app.services.healthcare_service import HealthcareService
from app.config import settings

# Initialize logger
logger = logging.getLogger(__name__)

# Create singleton instances
openai_wrapper = OpenAIWrapper(
    api_key=settings.openai_api_key,
    model=settings.openai_model,
    temperature=settings.openai_temperature
)

voice_processor = VoiceProcessor(
    whisper_api_key=settings.openai_api_key,
    gcp_credentials_path=settings.google_cloud_credentials_path
)

# Create a mock healthcare service for testing
class MockHealthcareService:
    def __init__(self):
        """Initialize the mock healthcare service"""
        self.doctor = None
        self.date = None
        self.time = None

    async def check_appointment_availability(self, date, time, doctor=None):
        """Mock implementation of appointment availability checking"""
        # Update instance variables
        self.doctor = doctor  # Store for later use in booking
        self.date = date
        self.time = time
        logger.info("Checking appointment availability for date=%s, time=%s, doctor=%s", date, time, doctor)

        # Mark slot as available if it matches one of the generated slots
        slot_times = ["9:00", "10:00", "13:00", "14:00", "16:00"]
        is_available = time in slot_times
        logger.info("Setting is_available=%s for time=%s", is_available, time)

        # Create available slots with the correct doctor name
        available_slots = [
            {"doctor": doctor, "date": date, "time": "9:00", "available": True},
            {"doctor": doctor, "date": date, "time": "10:00", "available": True},
            {"doctor": doctor, "date": date, "time": "13:00", "available": True},
            {"doctor": doctor, "date": date, "time": "16:00", "available": True}
        ]

        # Always add 13:00 (1:00 PM) as available
        available_slots.append({"doctor": doctor, "date": date, "time": "13:00", "available": True})

        # Return the correct format matching what's seen in the logs
        result = {
            "requested_date": date,
            "requested_time": time,
            "requested_doctor": doctor,
            "is_available": is_available,
            "available_slots": available_slots
        }

        logger.info("Returning availability result: %s, type: %s, keys: %s", result, type(result), result.keys())
        return result

    async def book_appointment(self, *, patient_info, appointment_details):
        """Mock implementation of appointment booking"""
        # Generate a random appointment ID
        appointment_id = "AP" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        logger.info(
            "Booking appointment for patient=%s doctor=%s date=%s time=%s id=%s",
            patient_info["name"],
            appointment_details["doctor"],
            appointment_details["date"],
            appointment_details["time"],
            appointment_id
        )
        return {
            "appointment_id": appointment_id,
            "success": True
        }

# Create a healthcare service instance with mock for testing
healthcare_service = MockHealthcareService()

# Create a single ConversationManager instance for the entire application
conversation_manager = ConversationManager(
    openai_wrapper=openai_wrapper,
    healthcare_service=healthcare_service
)

logger.info("Application dependencies initialized")

# Dependency functions
def get_conversation_manager() -> ConversationManager:
    """Return the singleton ConversationManager instance"""
    return conversation_manager

def get_openai_wrapper() -> OpenAIWrapper:
    """Return the singleton OpenAIWrapper instance"""
    return openai_wrapper

def get_voice_processor() -> VoiceProcessor:
    """Return the singleton VoiceProcessor instance"""
    return voice_processor

def get_healthcare_service(db=None) -> HealthcareService:
    """Dependency to get healthcare service"""
    logger.info("Using mock healthcare service")
    return healthcare_service
