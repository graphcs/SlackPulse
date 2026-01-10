"""Main notification monitoring orchestration."""

import logging
from datetime import datetime
from threading import Event
from typing import Optional, List, Dict, Any

from ..detectors.base import BaseDetector
from ..detectors.distributed import DistributedNotificationDetector
from ..detectors.filesystem import FileSystemDetector
from ..detectors.database import NotificationDatabaseDetector
from ..detectors.hybrid import HybridDetector
from ..filters.bot import BotFilter
from ..filters.deduplication import DeduplicationCache
from ..tts.speaker import Speaker
from ..sms.sender import TwilioSender
from .notification import SlackNotification

logger = logging.getLogger(__name__)


class NotificationMonitor:
    """
    Main monitoring orchestrator.

    Coordinates detectors, filters, and TTS to process Slack notifications.
    """

    def __init__(
        self,
        shutdown_event: Event,
        discovery_mode: bool = False,
        dry_run: bool = False,
        use_filesystem_fallback: bool = True,
        use_database: bool = False,
        tts_voice: str = "Samantha",
        tts_rate: int = 150,
        tts_enabled: bool = True,
        dedup_window: int = 30,
        sms_enabled: bool = False,
        sms_account_sid: str = "",
        sms_auth_token: str = "",
        sms_from_number: str = "",
        sms_to_number: str = "",
        sms_use_whatsapp: bool = False,
    ):
        """
        Initialize the notification monitor.

        Args:
            shutdown_event: Event to signal shutdown.
            discovery_mode: If True, log all notifications for discovery.
            dry_run: If True, print instead of TTS.
            use_filesystem_fallback: Use filesystem detector as fallback.
            use_database: Use notification database (requires Full Disk Access).
            tts_voice: Voice for TTS.
            tts_rate: Speech rate in WPM.
            tts_enabled: Whether to enable TTS.
            dedup_window: Deduplication window in seconds.
            sms_enabled: Whether to enable SMS/WhatsApp notifications.
            sms_account_sid: Twilio Account SID.
            sms_auth_token: Twilio Auth Token.
            sms_from_number: Twilio phone number.
            sms_to_number: Destination phone number.
            sms_use_whatsapp: Use WhatsApp instead of SMS.
        """
        self.shutdown_event = shutdown_event
        self.discovery_mode = discovery_mode
        self.dry_run = dry_run
        self.use_filesystem_fallback = use_filesystem_fallback
        self.use_database = True  # Always use database mode for actual message content

        # Components
        self._detectors: List[BaseDetector] = []
        self._bot_filter = BotFilter()
        self._dedup_cache = DeduplicationCache(window_seconds=dedup_window)
        self._speaker = Speaker(
            voice=tts_voice,
            rate=tts_rate,
            enabled=tts_enabled and not dry_run,
        )
        self._sms_sender = TwilioSender(
            account_sid=sms_account_sid,
            auth_token=sms_auth_token,
            from_number=sms_from_number,
            to_number=sms_to_number,
            enabled=sms_enabled and not dry_run,
            use_whatsapp=sms_use_whatsapp,
        )

        # Stats
        self._notifications_processed = 0
        self._notifications_filtered = 0

    def _handle_notification(
        self,
        sender: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle a detected notification.

        This is called by detectors when they detect activity.

        Args:
            sender: Message sender.
            message: Message content.
            metadata: Optional metadata from detector.
        """
        # Skip empty notifications
        if not sender or not message:
            return

        # Filter bots
        if self._bot_filter.is_bot_message(sender, message):
            self._notifications_filtered += 1
            logger.debug(f"Filtered bot message from: {sender}")
            return

        # Deduplicate
        if self._dedup_cache.is_duplicate(sender, message):
            self._notifications_filtered += 1
            return

        # Create notification object
        notification = SlackNotification(
            sender=sender,
            message=message,
            timestamp=datetime.now(),
            source=metadata.get("source", "unknown") if metadata else "unknown",
            metadata=metadata,
        )

        self._notifications_processed += 1

        # Announce
        self._announce_notification(notification)

    def _announce_notification(self, notification: SlackNotification) -> None:
        """Announce notification via TTS, SMS, or print."""
        log_msg = f"[{notification.timestamp.strftime('%H:%M:%S')}] {notification}"

        if self.dry_run:
            print(f"[DRY RUN] {log_msg}")
            logger.info(f"Dry run: {log_msg}")
        else:
            logger.info(log_msg)
            # TTS announcement
            self._speaker.speak_notification(
                notification.sender,
                notification.message,
            )
            # SMS notification
            self._sms_sender.send_notification(
                notification.sender,
                notification.message,
            )

    def start(self) -> None:
        """Start all detectors and begin monitoring."""
        logger.info("Starting SlackPulse notification monitor...")

        if self.discovery_mode:
            logger.info("=== DISCOVERY MODE ===")
            logger.info("Logging all distributed notifications to help identify Slack patterns.")
            logger.info("Send some Slack messages and watch the output.")
            logger.info("Press Ctrl+C to stop.")
            logger.info("=" * 40)

        # Use database detector to read actual message content
        if not self.discovery_mode:
            logger.info("Using notification database (requires Full Disk Access)")
            db_detector = NotificationDatabaseDetector(
                callback=self._handle_notification,
                shutdown_event=self.shutdown_event,
            )
            self._detectors.append(db_detector)
            db_detector.start()
        else:
            # Discovery mode only
            distributed_detector = DistributedNotificationDetector(
                callback=self._handle_notification,
                shutdown_event=self.shutdown_event,
                discovery_mode=self.discovery_mode,
            )
            self._detectors.append(distributed_detector)
            distributed_detector.start()

        logger.info(f"Started {len(self._detectors)} detector(s)")

    def run(self) -> None:
        """Run the monitor until shutdown."""
        self.start()

        # Wait for shutdown signal
        try:
            while not self.shutdown_event.is_set():
                self.shutdown_event.wait(timeout=1.0)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")

        self.stop()

    def stop(self) -> None:
        """Stop all detectors and clean up."""
        logger.info("Stopping SlackPulse...")

        for detector in self._detectors:
            try:
                detector.stop()
            except Exception as e:
                logger.error(f"Error stopping {detector.name}: {e}")

        self._speaker.stop()

        logger.info(
            f"Processed {self._notifications_processed} notifications, "
            f"filtered {self._notifications_filtered}"
        )
        logger.info("SlackPulse stopped")
