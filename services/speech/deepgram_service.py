from deepgram import (
    DeepgramClient,
    LiveOptions,
    LiveTranscriptionEvents,
)
import os
import json
import logging
from typing import AsyncGenerator, Callable
import asyncio

logger = logging.getLogger(__name__)

class DeepgramService:
    def __init__(self):
        # Initialize with new DeepgramClient
        self.client = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
        
    async def create_live_transcription(self, callback: Callable, max_retries: int = 3):
        """Create a live transcription connection with Deepgram"""
        for attempt in range(max_retries):
            try:
                # Configure Deepgram with optimal settings for phone calls
                options = LiveOptions(
                    model="nova-2",  # Using latest Nova-2 model
                    smart_format=True,
                    language="en-US",
                    interim_results=False,
                    punctuate=True,
                    endpointing=True,
                    utterance_end_ms=1000,
                    encoding="linear16",  # PCM-16
                    sample_rate=8000,  # Phone call sample rate
                )
                
                # Add detailed logging
                logger.info("Creating Deepgram connection...")
                connection = await self.client.listen.live.v("1")
                connection.start(options)
                logger.info("Deepgram connection established successfully")
                return connection
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to connect after {max_retries} attempts")
                    raise
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(1)

    async def process_audio(self, audio_data: bytes, connection):
        """Send audio data to Deepgram"""
        try:
            if not audio_data:
                logger.warning("Received empty audio data")
                return
            if len(audio_data) < 32:  # Minimum reasonable size for audio chunk
                logger.warning(f"Audio chunk too small: {len(audio_data)} bytes")
                return
            await connection.send_audio(audio_data)
        except Exception as e:
            logger.error(f"Error sending audio to Deepgram: {e}")
            raise

    async def get_transcription(self, connection) -> AsyncGenerator[str, None]:
        """Get transcription results from Deepgram"""
        try:
            async for event in connection:
                if event.type == LiveTranscriptionEvents.TRANSCRIPT:
                    if event.is_final:
                        transcript = event.channel.alternatives[0].transcript
                        if transcript.strip():
                            # Add clear terminal output for transcription
                            logger.info(f"\n🎤 User said: {transcript}")
                            yield transcript
                        
        except Exception as e:
            logger.error(f"Error receiving transcription from Deepgram: {e}")
            raise

    async def close_connection(self, connection):
        """Close the Deepgram connection"""
        try:
            await connection.finish()
        except Exception as e:
            logger.error(f"Error closing Deepgram connection: {e}")
            raise 