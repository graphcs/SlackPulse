"""NSDistributedNotificationCenter observer for detecting Slack notifications."""

import logging
import threading
from typing import Callable, Optional, Set
from threading import Event

from Foundation import (
    NSObject,
    NSDistributedNotificationCenter,
    NSRunLoop,
    NSDate,
    NSDefaultRunLoopMode,
)
import objc

from .base import BaseDetector

logger = logging.getLogger(__name__)


class NotificationObserver(NSObject):
    """Objective-C observer class for distributed notifications."""

    def initWithCallback_discoveryMode_(self, callback, discovery_mode):
        """Initialize with Python callback."""
        self = objc.super(NotificationObserver, self).init()
        if self is None:
            return None
        self._callback = callback
        self._discovery_mode = discovery_mode
        self._slack_patterns = {
            "slack",
            "tinyspeck",
            "slackmacgap",
        }
        return self

    def handleNotification_(self, notification):
        """Handle incoming distributed notification."""
        try:
            name = notification.name()
            obj = notification.object()
            user_info = notification.userInfo()

            name_str = str(name) if name else ""
            obj_str = str(obj) if obj else ""

            # In discovery mode, log everything
            if self._discovery_mode:
                logger.info(f"[DISCOVERY] name={name_str}, object={obj_str}, info={user_info}")
                return

            # Check if this is Slack-related
            name_lower = name_str.lower()
            obj_lower = obj_str.lower()

            is_slack = any(
                pattern in name_lower or pattern in obj_lower
                for pattern in self._slack_patterns
            )

            if is_slack:
                logger.debug(f"Slack notification: {name_str}")
                # Try to extract sender/message from userInfo
                sender, message = self._extract_message_info(user_info, name_str)
                if sender and message:
                    self._callback(sender, message, {"source": "distributed", "name": name_str})

        except Exception as e:
            logger.error(f"Error handling notification: {e}", exc_info=True)

    def _extract_message_info(self, user_info, name: str) -> tuple[str, str]:
        """Extract sender and message from notification userInfo."""
        if not user_info:
            return "", ""

        # Try common keys that Slack might use
        sender = ""
        message = ""

        # Check for title/body pattern
        if "title" in user_info:
            sender = str(user_info["title"])
        elif "sender" in user_info:
            sender = str(user_info["sender"])
        elif "from" in user_info:
            sender = str(user_info["from"])

        if "body" in user_info:
            message = str(user_info["body"])
        elif "message" in user_info:
            message = str(user_info["message"])
        elif "text" in user_info:
            message = str(user_info["text"])

        return sender, message


class DistributedNotificationDetector(BaseDetector):
    """
    Detector using NSDistributedNotificationCenter.

    This listens for distributed notifications broadcast by apps.
    No special permissions required.
    """

    def __init__(
        self,
        callback: Callable[[str, str, Optional[dict]], None],
        shutdown_event: Event,
        discovery_mode: bool = False,
        notification_names: Optional[Set[str]] = None,
    ):
        """
        Initialize the distributed notification detector.

        Args:
            callback: Function to call when Slack notification detected.
            shutdown_event: Event to signal shutdown.
            discovery_mode: If True, log all notifications for discovery.
            notification_names: Specific notification names to listen for.
                               If None, listens to all notifications.
        """
        super().__init__(callback, shutdown_event)
        self.discovery_mode = discovery_mode
        self.notification_names = notification_names
        self._observer: Optional[NotificationObserver] = None
        self._center: Optional[NSDistributedNotificationCenter] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    @property
    def name(self) -> str:
        return "DistributedNotificationDetector"

    def start(self) -> None:
        """Start listening for distributed notifications."""
        if self._running:
            logger.warning("Detector already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"Started {self.name} "
            f"(discovery_mode={self.discovery_mode})"
        )

    def _run_loop(self) -> None:
        """Run the notification observation loop."""
        try:
            # Create observer
            self._observer = NotificationObserver.alloc().initWithCallback_discoveryMode_(
                self.callback, self.discovery_mode
            )

            # Get the distributed notification center
            self._center = NSDistributedNotificationCenter.defaultCenter()

            # Register for notifications
            if self.notification_names:
                # Listen to specific notification names
                for notif_name in self.notification_names:
                    self._center.addObserver_selector_name_object_(
                        self._observer,
                        "handleNotification:",
                        notif_name,
                        None,
                    )
                    logger.debug(f"Listening for: {notif_name}")
            else:
                # Listen to all notifications (for discovery or broad monitoring)
                self._center.addObserver_selector_name_object_(
                    self._observer,
                    "handleNotification:",
                    None,  # All notification names
                    None,  # All sending objects
                )
                logger.debug("Listening for all distributed notifications")

            # Run the event loop
            run_loop = NSRunLoop.currentRunLoop()
            while self._running and not self.shutdown_event.is_set():
                # Run loop for a short interval, then check shutdown
                run_loop.runMode_beforeDate_(
                    NSDefaultRunLoopMode,
                    NSDate.dateWithTimeIntervalSinceNow_(0.5),
                )

        except Exception as e:
            logger.error(f"Error in notification loop: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up notification center registration."""
        if self._center and self._observer:
            try:
                self._center.removeObserver_(self._observer)
            except Exception as e:
                logger.debug(f"Error removing observer: {e}")
        self._center = None
        self._observer = None

    def stop(self) -> None:
        """Stop the detector."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info(f"Stopped {self.name}")
