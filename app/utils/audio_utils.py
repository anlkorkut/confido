import os
import tempfile
import logging
from typing import BinaryIO, Optional

from pydub import AudioSegment
import numpy as np

logger = logging.getLogger(__name__)

def save_audio_file(audio_data: bytes, file_format: str = "mp3") -> str:
    """Save audio data to a temporary file"""
    try:
        # Create a temporary file with the appropriate extension
        with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_data)
        
        logger.debug("Audio file saved to %s", temp_path)
        return temp_path
    except Exception as e:
        logger.error("Error saving audio file: %s", str(e))
        raise

def convert_audio_format(input_file: str, output_format: str = "wav") -> str:
    """Convert audio file to a different format"""
    try:
        # Load the audio file
        audio = AudioSegment.from_file(input_file)
        
        # Create a temporary file for the output
        with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as temp_file:
            output_path = temp_file.name
        
        # Export to the new format
        audio.export(output_path, format=output_format)
        
        logger.debug("Audio converted from %s to %s format", input_file, output_path)
        return output_path
    except Exception as e:
        logger.error("Error converting audio format: %s", str(e))
        raise

def normalize_audio(input_file: str) -> str:
    """Normalize audio volume and convert to mono if needed"""
    try:
        # Load the audio file
        audio = AudioSegment.from_file(input_file)
        
        # Convert to mono if stereo
        if audio.channels > 1:
            audio = audio.set_channels(1)
        
        # Normalize volume
        audio = audio.normalize()
        
        # Create a temporary file for the normalized audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            output_path = temp_file.name
        
        # Export to WAV format
        audio.export(output_path, format="wav")
        
        logger.debug("Audio normalized: %s", output_path)
        return output_path
    except Exception as e:
        logger.error("Error normalizing audio: %s", str(e))
        raise

def get_audio_duration(file_path: str) -> float:
    """Get the duration of an audio file in seconds"""
    try:
        audio = AudioSegment.from_file(file_path)
        duration_seconds = len(audio) / 1000.0  # Convert milliseconds to seconds
        return duration_seconds
    except Exception as e:
        logger.error("Error getting audio duration: %s", str(e))
        return 0.0

def validate_audio_file(file_path: str) -> bool:
    """Validate if the file is a valid audio file"""
    try:
        # Check file extension
        valid_extensions = [".wav", ".mp3", ".ogg", ".flac"]
        if not any(file_path.lower().endswith(ext) for ext in valid_extensions):
            logger.warning("Unsupported file extension: %s", file_path)
            return False
        
        # Try to load the file
        audio = AudioSegment.from_file(file_path)
        
        # Check duration (reject if too long or too short)
        duration_ms = len(audio)
        if duration_ms < 500 or duration_ms > 300000:  # Between 0.5s and 5 minutes
            logger.warning("Audio duration outside acceptable range: %s ms", duration_ms)
            return False
        
        return True
    except Exception as e:
        logger.warning("Audio validation failed: %s", str(e))
        return False

def cleanup_temp_files(file_paths: list):
    """Clean up temporary audio files"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug("Removed temporary file: %s", file_path)
        except Exception as e:
            logger.warning("Failed to remove temporary file %s: %s", file_path, str(e))