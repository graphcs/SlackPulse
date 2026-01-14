"""Configuration management for SlackPulse."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


@dataclass
class TTSConfig:
    """TTS configuration."""

    voice: str = "nova"  # OpenAI voice (nova, alloy, echo, fable, onyx, shimmer)
    rate: int = 150  # Words per minute (only for macOS fallback)
    enabled: bool = True
    use_openai: bool = True  # Use OpenAI TTS for natural speech


@dataclass
class FilterConfig:
    """Filter configuration."""

    # Bot detection patterns (regex, case-insensitive)
    bot_patterns: List[str] = field(
        default_factory=lambda: [
            r"\bbot\b",
            r"slackbot",
            r"workflow",
            r"automation",
        ]
    )

    # Bot message keywords (substring match)
    bot_keywords: List[str] = field(
        default_factory=lambda: [
            "has joined the channel",
            "has left the channel",
            "set the channel topic",
        ]
    )

    dedup_window_seconds: int = 30


@dataclass
class MonitorConfig:
    """Monitor configuration."""

    use_filesystem_fallback: bool = True


@dataclass
class SMSConfig:
    """SMS/WhatsApp configuration for Twilio."""

    enabled: bool = False
    account_sid: str = ""
    auth_token: str = ""
    from_number: str = ""
    to_number: str = ""
    use_whatsapp: bool = False  # Use WhatsApp instead of SMS (no A2P registration needed)


@dataclass
class Config:
    """Main configuration."""

    tts: TTSConfig = field(default_factory=TTSConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    sms: SMSConfig = field(default_factory=SMSConfig)
    log_file: Optional[Path] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create Config from dictionary."""
        return cls(
            tts=TTSConfig(**data.get("tts", {})),
            filters=FilterConfig(**data.get("filters", {})),
            monitor=MonitorConfig(**data.get("monitor", {})),
            sms=SMSConfig(**data.get("sms", {})),
            log_file=Path(data["log_file"]) if data.get("log_file") else None,
        )


def load_config(path: Path) -> Config:
    """
    Load configuration from TOML file.

    Args:
        path: Path to config file.

    Returns:
        Config object (defaults if file doesn't exist).
    """
    if not path.exists():
        return Config()

    if tomllib is None:
        # Can't parse TOML without tomllib/tomli
        return Config()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return Config.from_dict(data)


def get_default_config_toml() -> str:
    """Return default configuration as TOML string."""
    return '''# SlackPulse Configuration

[tts]
voice = "Samantha"    # Use `say -v '?'` to list available voices
rate = 200            # Words per minute (150-250 recommended)
enabled = true

[filters]
# Patterns to identify bot senders (regex, case-insensitive)
bot_patterns = ["\\\\bbot\\\\b", "slackbot", "workflow", "automation"]

# Message content that indicates automated messages
bot_keywords = [
    "has joined the channel",
    "has left the channel",
    "set the channel topic",
]

dedup_window_seconds = 30

[monitor]
use_filesystem_fallback = true

# SMS notifications via Twilio (optional)
# Get credentials at https://console.twilio.com/
[sms]
enabled = false
# account_sid = "ACxxxxxxxxxx"
# auth_token = "xxxxxxxxxx"
# from_number = "+1234567890"
# to_number = "+0987654321"

# Uncomment to enable file logging
# log_file = "~/.local/share/slackpulse/slackpulse.log"
'''
