"""Notification data structures."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class SlackNotification:
    """Processed Slack notification ready for TTS."""

    sender: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"  # "distributed" or "filesystem"
    metadata: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return f"{self.sender}: {self.message}"

    def __repr__(self) -> str:
        return (
            f"SlackNotification(sender={self.sender!r}, "
            f"message={self.message!r}, source={self.source!r})"
        )
