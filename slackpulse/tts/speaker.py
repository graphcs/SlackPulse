"""Text-to-speech using OpenAI API or macOS built-in `say` command."""

import os
import subprocess
import tempfile
import logging
from typing import Optional, List
from pathlib import Path

from dotenv import load_dotenv, set_key

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# OpenAI TTS voices
OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

# Path to .env file (in project root)
ENV_FILE = Path(__file__).parent.parent.parent / ".env"


def _get_env_file_path() -> Path:
    """Get the path to the .env file."""
    # Try project root first
    if ENV_FILE.exists():
        return ENV_FILE
    # Create if doesn't exist
    return ENV_FILE


def _prompt_for_api_key() -> Optional[str]:
    """Prompt user to enter their OpenAI API key."""
    print("\n" + "=" * 60)
    print("OpenAI API key not found or invalid.")
    print("Get your API key at: https://platform.openai.com/api-keys")
    print("=" * 60)
    print("\nPaste your OpenAI API key (or press Enter to skip):")

    try:
        api_key = input("> ").strip()
        if api_key:
            return api_key
    except (EOFError, KeyboardInterrupt):
        pass

    return None


def _validate_api_key(api_key: str) -> bool:
    """Validate an OpenAI API key by making a test request."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # Make a minimal API call to validate
        client.models.list()
        return True
    except Exception as e:
        logger.debug(f"API key validation failed: {e}")
        return False


def _save_api_key(api_key: str) -> bool:
    """Save the API key to .env file."""
    try:
        env_path = _get_env_file_path()

        # Create .env if it doesn't exist
        if not env_path.exists():
            env_path.write_text("# SlackPulse Environment Variables\n# DO NOT commit this file to git\n\n")

        # Save using dotenv
        set_key(str(env_path), "OPENAI_API_KEY", api_key)

        # Also set in current environment
        os.environ["OPENAI_API_KEY"] = api_key

        print(f"API key saved to {env_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save API key: {e}")
        return False


class Speaker:
    """
    Text-to-speech wrapper.

    Uses OpenAI TTS API for natural speech, with fallback to macOS `say` command.
    """

    def __init__(
        self,
        voice: str = "nova",
        rate: int = 150,
        enabled: bool = True,
        use_openai: bool = True,
        prompt_for_key: bool = True,
    ):
        """
        Initialize the speaker.

        Args:
            voice: Voice name. For OpenAI: alloy, echo, fable, onyx, nova, shimmer.
                   For macOS: use `say -v '?'` to list.
            rate: Words per minute (only used for macOS fallback).
            enabled: Whether TTS is enabled.
            use_openai: Use OpenAI TTS (recommended for natural speech).
            prompt_for_key: Prompt user for API key if missing/invalid.
        """
        self.voice = voice
        self.rate = rate
        self.enabled = enabled
        self.use_openai = use_openai
        self.prompt_for_key = prompt_for_key
        self._process: Optional[subprocess.Popen] = None
        self._openai_client = None

        if self.use_openai:
            self._init_openai()

    def _init_openai(self) -> None:
        """Initialize OpenAI client, prompting for key if needed."""
        api_key = os.getenv("OPENAI_API_KEY")

        # If no key, prompt for one
        if not api_key and self.prompt_for_key:
            api_key = _prompt_for_api_key()
            if api_key:
                if _validate_api_key(api_key):
                    _save_api_key(api_key)
                    print("API key validated and saved successfully!")
                else:
                    print("Invalid API key. Falling back to macOS TTS.")
                    api_key = None

        if not api_key:
            if self.prompt_for_key:
                print("No API key provided. Using macOS TTS (robotic voice).")
            else:
                logger.warning("OPENAI_API_KEY not set, falling back to macOS TTS")
            self.use_openai = False
            return

        try:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=api_key)

            # Validate the key works
            try:
                self._openai_client.models.list()
                logger.info("OpenAI TTS initialized")
            except Exception as e:
                if self.prompt_for_key:
                    print(f"API key invalid: {e}")
                    # Prompt for new key
                    new_key = _prompt_for_api_key()
                    if new_key and _validate_api_key(new_key):
                        _save_api_key(new_key)
                        self._openai_client = OpenAI(api_key=new_key)
                        print("API key validated and saved successfully!")
                        logger.info("OpenAI TTS initialized")
                    else:
                        print("Using macOS TTS instead.")
                        self.use_openai = False
                        self._openai_client = None
                else:
                    logger.error(f"OpenAI API key invalid: {e}")
                    self.use_openai = False
                    self._openai_client = None

        except ImportError:
            logger.error("openai package not installed. Run: pip install openai")
            self.use_openai = False
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI: {e}")
            self.use_openai = False

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

        # Sanitize text
        text = self._sanitize_text(text)

        if self.use_openai and self._openai_client:
            self._speak_openai(text)
        else:
            self._speak_macos(text)

    def _speak_openai(self, text: str) -> None:
        """Speak using OpenAI TTS API."""
        try:
            # Generate speech
            response = self._openai_client.audio.speech.create(
                model="tts-1",
                voice=self.voice if self.voice in OPENAI_VOICES else "nova",
                input=text,
            )

            # Save to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name
                response.stream_to_file(temp_path)

            # Play audio asynchronously
            self._process = subprocess.Popen(
                ["afplay", temp_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug(f"Speaking (OpenAI): {text[:50]}...")

            # Clean up temp file after playback (in background)
            def cleanup():
                if self._process:
                    self._process.wait()
                try:
                    os.unlink(temp_path)
                except:
                    pass

            import threading
            threading.Thread(target=cleanup, daemon=True).start()

        except Exception as e:
            logger.error(f"OpenAI TTS error: {e}, falling back to macOS")
            self._speak_macos(text)

    def _speak_macos(self, text: str) -> None:
        """Speak using macOS say command (fallback)."""
        cmd = [
            "say",
            "-v", self.voice if self.voice not in OPENAI_VOICES else "Samantha",
            "-r", str(self.rate),
            text,
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug(f"Speaking (macOS): {text[:50]}...")

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
        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        text = text.replace("\t", " ")
        while "  " in text:
            text = text.replace("  ", " ")
        return text.strip()

    @staticmethod
    def list_voices() -> List[str]:
        """List available voices."""
        voices = ["OpenAI voices: " + ", ".join(OPENAI_VOICES)]
        try:
            result = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            voices.append("macOS voices:")
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split()
                    if parts:
                        voices.append(f"  {parts[0]}")
        except Exception as e:
            logger.error(f"Failed to list macOS voices: {e}")
        return voices
