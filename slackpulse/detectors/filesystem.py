"""File system monitoring detector for Slack activity."""

import logging
import os
import time
import threading
from pathlib import Path
from typing import Callable, Optional, Set
from threading import Event

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .base import BaseDetector

logger = logging.getLogger(__name__)


class SlackFileHandler(FileSystemEventHandler):
    """Handle file system events in Slack's data directory."""

    # Files/paths that indicate message activity
    ACTIVITY_PATTERNS = {
        "Local Storage",
        "leveldb",
        "IndexedDB",
        ".log",
        "Cache",
    }

    # Paths to ignore (noisy, not message-related)
    IGNORE_PATTERNS = {
        "GPUCache",
        "Code Cache",
        "blob_storage",
        "Session Storage",
        ".tmp",
    }

    def __init__(
        self,
        callback: Callable[[], None],
        debounce_seconds: float = 1.0,
    ):
        """
        Initialize the file handler.

        Args:
            callback: Function to call when Slack activity detected.
            debounce_seconds: Minimum time between callback invocations.
        """
        super().__init__()
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._last_callback_time: float = 0
        self._lock = threading.Lock()

    def _should_ignore(self, path: str) -> bool:
        """Check if this path should be ignored."""
        for pattern in self.IGNORE_PATTERNS:
            if pattern in path:
                return True
        return False

    def _is_activity_indicator(self, path: str) -> bool:
        """Check if this path indicates message activity."""
        for pattern in self.ACTIVITY_PATTERNS:
            if pattern in path:
                return True
        return False

    def _trigger_callback(self) -> None:
        """Trigger callback with debouncing."""
        with self._lock:
            now = time.time()
            if now - self._last_callback_time >= self._debounce_seconds:
                self._last_callback_time = now
                try:
                    self._callback()
                except Exception as e:
                    logger.error(f"Error in file event callback: {e}")

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        path = event.src_path
        if self._should_ignore(path):
            return

        if self._is_activity_indicator(path):
            logger.debug(f"Slack activity detected: {path}")
            self._trigger_callback()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return

        path = event.src_path
        if self._should_ignore(path):
            return

        if self._is_activity_indicator(path):
            logger.debug(f"Slack file created: {path}")
            self._trigger_callback()


class FileSystemDetector(BaseDetector):
    """
    Detector using file system monitoring.

    Watches Slack's data directory for file changes that indicate
    new message activity. This is a fallback when distributed
    notifications don't provide enough information.

    No special permissions required (just normal file access).
    """

    DEFAULT_SLACK_PATH = Path.home() / "Library" / "Application Support" / "Slack"

    def __init__(
        self,
        callback: Callable[[str, str, Optional[dict]], None],
        shutdown_event: Event,
        slack_path: Optional[Path] = None,
        debounce_seconds: float = 1.0,
    ):
        """
        Initialize the filesystem detector.

        Args:
            callback: Function to call when activity detected.
                      Note: For filesystem detection, sender/message are generic.
            shutdown_event: Event to signal shutdown.
            slack_path: Path to Slack's data directory.
            debounce_seconds: Minimum time between detections.
        """
        super().__init__(callback, shutdown_event)
        self.slack_path = slack_path or self.DEFAULT_SLACK_PATH
        self.debounce_seconds = debounce_seconds
        self._observer: Optional[Observer] = None
        self._handler: Optional[SlackFileHandler] = None

    @property
    def name(self) -> str:
        return "FileSystemDetector"

    def _on_activity_detected(self) -> None:
        """Called when file activity indicates a new message."""
        # With filesystem monitoring, we can't extract actual message content
        # Just signal that there's new Slack activity
        self.callback(
            "Slack",
            "New activity detected",
            {"source": "filesystem", "path": str(self.slack_path)},
        )

    def start(self) -> None:
        """Start watching Slack's data directory."""
        if not self.slack_path.exists():
            logger.warning(f"Slack data directory not found: {self.slack_path}")
            logger.warning("Is Slack installed? Filesystem detection disabled.")
            return

        self._handler = SlackFileHandler(
            callback=self._on_activity_detected,
            debounce_seconds=self.debounce_seconds,
        )

        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self.slack_path),
            recursive=True,
        )
        self._observer.start()
        logger.info(f"Started {self.name} watching: {self.slack_path}")

    def stop(self) -> None:
        """Stop the filesystem observer."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        logger.info(f"Stopped {self.name}")
