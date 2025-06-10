from pydantic_settings import BaseSettings
from typing import Dict

class Settings(BaseSettings):
    # OpenAI Configuration
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.7
    
    # Google Cloud Configuration
    google_cloud_credentials_path: str
    tts_voice_name: str = "en-US-Journey-F"
    tts_language_code: str = "en-US"
    
    # Database Configuration
    database_url: str = "sqlite:///./healthcare_assistant.db"
    
    # Application Configuration
    app_name: str = "Healthcare Voice Assistant"
    clinic_name: str = "Confido Health Clinic"
    
    class Config:
        env_file = ".env"

settings = Settings()