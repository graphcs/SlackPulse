"""Base detector interface for SlackPulse."""

from abc import ABC, abstractmethod
from typing import Callable, Optional
from threading import Event


class BaseDetector(ABC):
    """Abstract base class for notification detectors."""

    def __init__(
        self,
        callback: Callable[[str, str, Optional[dict]], None],
        shutdown_event: Event,
    ):
        """
        Initialize the detector.

        Args:
            callback: Function to call when notification detected.
                      Signature: (sender: str, message: str, metadata: dict | None)
            shutdown_event: Event to signal shutdown.
        """
        self.callback = callback
        self.shutdown_event = shutdown_event

    @abstractmethod
    def start(self) -> None:
        """Start the detector. This may block or run in background."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the detector and clean up resources."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return detector name for logging."""
        pass
