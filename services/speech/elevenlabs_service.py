from elevenlabs.client import AsyncElevenLabs
import os
import logging
from typing import Optional
import re
import asyncio  # Add for timeout handling

logger = logging.getLogger(__name__)

class ElevenLabsService:
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not found in environment variables")
        
        self.client = AsyncElevenLabs(api_key=self.api_key)
        
        # Enhanced voice settings for more natural conversation
        self.voice_settings = {
            "stability": 0.71,
            "similarity_boost": 0.5,
            "style": 0.35,
            "use_speaker_boost": True
        }
        
        # Rachel voice (most natural)
        self.default_voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        if not self.default_voice_id:
            logger.warning("ELEVENLABS_VOICE_ID not set, using default Rachel voice")
            self.default_voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice

    async def generate_speech(self, 
                            text: str, 
                            voice_id: Optional[str] = None,
                            add_natural_pauses: bool = True,
                            timeout: float = 10.0) -> bytes:
        """
        Generate speech using ElevenLabs API
        
        Args:
            text: Text to convert to speech
            voice_id: Optional voice ID to use
            add_natural_pauses: Whether to add pauses for natural speech
            timeout: Timeout in seconds for the API call
        
        Returns:
            bytes: Audio data in MP3 format
        """
        try:
            if not text.strip():
                raise ValueError("Empty text provided")

            formatted_text = self._format_text_for_natural_speech(text) if add_natural_pauses else text
            logger.info(f"Generating speech for: {formatted_text}")
            
            voice_id = voice_id or self.default_voice_id
            
            # Truncate text if needed
            max_characters = 300
            if len(formatted_text) > max_characters:
                truncated_text = re.split(r'([.!?])', formatted_text[:max_characters])[0]
                truncated_text = truncated_text.strip() + "..."
                logger.info(f"Text truncated from {len(formatted_text)} to {len(truncated_text)} characters")
            else:
                truncated_text = formatted_text
            
            # Generate audio using the async client with timeout
            try:
                audio_response = await asyncio.wait_for(
                    self.client.generate(
                        text=truncated_text,
                        voice=voice_id,
                        model="eleven_flash_v2_5"
                    ),
                    timeout=timeout
                )
                
                # Collect all chunks into a single bytes object
                audio_data = b""
                async for chunk in audio_response:
                    if not chunk:  # Skip empty chunks
                        continue
                    audio_data += chunk
                
                if not audio_data:
                    raise ValueError("No audio data generated")
                
                return audio_data
                
            except asyncio.TimeoutError:
                logger.error(f"Timeout after {timeout} seconds while generating speech")
                raise TimeoutError(f"Speech generation timed out after {timeout} seconds")
                
        except Exception as e:
            logger.error(f"Error generating speech: {str(e)}")
            raise

    def _format_text_for_natural_speech(self, text: str) -> str:
        """
        Format text to sound more natural with appropriate pauses
        
        Args:
            text: Input text to format
            
        Returns:
            str: Formatted text with natural pauses
        """
        if not isinstance(text, str):
            text = str(text)
            
        text = text.replace('.', '... ')
        text = text.replace('?', '...? ')
        text = text.replace('!', '...! ')
        text = text.replace(',', '... ')
        
        # Remove multiple spaces and trim
        return ' '.join(text.split())