"""Text-to-speech using macOS built-in `say` command."""

import subprocess
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class Speaker:
    """
    macOS text-to-speech wrapper.

    Uses the `say` command for simplicity and reliability.
    """

    def __init__(
        self,
        voice: str = "Samantha",
        rate: int = 150,
        enabled: bool = True,
    ):
        """
        Initialize the speaker.

        Args:
            voice: Voice name (use `say -v '?'` to list).
            rate: Words per minute (150-250 recommended).
            enabled: Whether TTS is enabled.
        """
        self.voice = voice
        self.rate = rate
        self.enabled = enabled
        self._process: Optional[subprocess.Popen] = None

    def speak(self, text: str) -> None:
        """
        Speak the given text.

        Interrupts any currently speaking text.

        Args:
            text: Text to speak.
        """
        if not self.enabled:
            logger.debug(f"TTS disabled, would say: {text}")
            return

        # Stop any current speech
        self.stop()

        # Sanitize text for shell safety
        text = self._sanitize_text(text)

        # Build command
        cmd = [
            "say",
            "-v", self.voice,
            "-r", str(self.rate),
            text,
        ]

        try:
            # Run asynchronously so we don't block
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug(f"Speaking: {text[:50]}...")

        except FileNotFoundError:
            logger.error("'say' command not found - TTS unavailable")
        except Exception as e:
            logger.error(f"TTS error: {e}")

    def speak_notification(self, sender: str, message: str) -> None:
        """
        Speak a notification in natural format.

        Args:
            sender: Message sender name.
            message: Message content.
        """
        # Truncate long messages
        max_message_len = 200
        if len(message) > max_message_len:
            message = message[:max_message_len] + "..."

        text = f"Message from {sender}: {message}"
        self.speak(text)

    def stop(self) -> None:
        """Stop any current speech."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        return self._process is not None and self._process.poll() is None

    def _sanitize_text(self, text: str) -> str:
        """Sanitize text for TTS."""
        # Remove or replace problematic characters
        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        text = text.replace("\t", " ")
        # Collapse multiple spaces
        while "  " in text:
            text = text.replace("  ", " ")
        return text.strip()

    @staticmethod
    def list_voices() -> List[str]:
        """List available voices."""
        try:
            result = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            voices = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    # Format: "VoiceName    lang    # description"
                    parts = line.split()
                    if parts:
                        voices.append(parts[0])
            return voices
        except Exception as e:
            logger.error(f"Failed to list voices: {e}")
            return []
