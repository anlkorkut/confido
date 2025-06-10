import os
import logging
import tempfile
from typing import Dict, Optional, BinaryIO

import openai
from google.cloud import texttospeech
from pydub import AudioSegment
import soundfile as sf
import numpy as np

class VoiceProcessor:
    def __init__(self, whisper_api_key: str, gcp_credentials_path: str):
        # Initialize Whisper API client
        self.openai_client = openai.OpenAI(api_key=whisper_api_key)
        
        # Initialize Google Cloud TTS client
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gcp_credentials_path
        self.tts_client = texttospeech.TextToSpeechClient()
        
        self.logger = logging.getLogger(__name__)
        
    async def transcribe_audio(self, audio_file_path: str) -> str:
        """Convert audio to text using Whisper API"""
        # Validate file format
        if not self._validate_audio_format(audio_file_path):
            raise ValueError(f"Invalid audio format for file: {audio_file_path}")
        
        try:
            # Preprocess audio for optimal STT performance
            processed_file_path = self._preprocess_audio(audio_file_path)
            
            # Open the processed audio file
            with open(processed_file_path, "rb") as audio_file:
                # Call Whisper API
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
                
            # Clean up temporary file if it was created
            if processed_file_path != audio_file_path and os.path.exists(processed_file_path):
                os.remove(processed_file_path)
                
            return response
            
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {str(e)}")
            raise
        
    async def synthesize_speech(self, text: str, voice_config: Dict) -> bytes:
        """Convert text to speech using Google Cloud TTS"""
        try:
            # Prepare text input
            synthesis_input = texttospeech.SynthesisInput(text=text)
            
            # Configure voice
            voice = texttospeech.VoiceSelectionParams(
                language_code=voice_config.get("language_code", "en-US"),
                name=voice_config.get("name", "en-US-Journey-F"),
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
            )
            
            # Configure audio
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=voice_config.get("speaking_rate", 1.0),
                pitch=voice_config.get("pitch", 0.0),
                effects_profile_id=["telephony-class-application"]
            )
            
            # Generate speech
            response = self.tts_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            return response.audio_content
            
        except Exception as e:
            self.logger.error(f"Error synthesizing speech: {str(e)}")
            raise
        
    def _validate_audio_format(self, file_path: str) -> bool:
        """Validate audio file format and quality"""
        try:
            # Check file extension
            valid_extensions = [".wav", ".mp3", ".ogg", ".flac"]
            if not any(file_path.lower().endswith(ext) for ext in valid_extensions):
                self.logger.warning(f"Unsupported file extension: {file_path}")
                return False
            
            # Load audio file to check if it's valid
            audio = AudioSegment.from_file(file_path)
            
            # Check duration (reject if too long or too short)
            duration_ms = len(audio)
            if duration_ms < 500 or duration_ms > 300000:  # Between 0.5s and 5 minutes
                self.logger.warning(f"Audio duration outside acceptable range: {duration_ms}ms")
                return False
                
            return True
            
        except Exception as e:
            self.logger.warning(f"Audio validation failed: {str(e)}")
            return False
        
    def _preprocess_audio(self, file_path: str) -> str:
        """Normalize audio for optimal STT performance"""
        try:
            # Load audio
            audio = AudioSegment.from_file(file_path)
            
            # Convert to mono if stereo
            if audio.channels > 1:
                audio = audio.set_channels(1)
            
            # Normalize volume
            audio = audio.normalize()
            
            # Ensure proper sample rate (16kHz is optimal for Whisper)
            if audio.frame_rate != 16000:
                audio = audio.set_frame_rate(16000)
            
            # Create a temporary file for the processed audio
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
                
            # Export to WAV format
            audio.export(temp_path, format="wav")
            
            return temp_path
            
        except Exception as e:
            self.logger.warning(f"Audio preprocessing failed: {str(e)}. Using original file.")
            return file_path