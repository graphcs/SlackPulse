"""Notification database detector for reading actual Slack message content."""

import logging
import os
import plistlib
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Set
from threading import Event

from .base import BaseDetector

logger = logging.getLogger(__name__)

# Mac epoch offset: seconds between Unix epoch (1970) and Mac epoch (2001)
MAC_EPOCH_OFFSET = 978307200

# Slack bundle identifier
SLACK_BUNDLE_ID = "com.tinyspeck.slackmacgap"


def get_darwin_user_dir() -> Optional[Path]:
    """Get the DARWIN_USER_DIR using getconf."""
    try:
        result = subprocess.run(
            ["getconf", "DARWIN_USER_DIR"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception as e:
        logger.debug(f"Failed to get DARWIN_USER_DIR: {e}")
    return None


def find_notification_database() -> Optional[Path]:
    """Find the notification database path."""
    # Try macOS Sequoia+ location first
    sequoia_path = (
        Path.home()
        / "Library"
        / "Group Containers"
        / "group.com.apple.usernoted"
        / "db2"
        / "db"
    )
    if sequoia_path.exists():
        return sequoia_path

    # Try legacy location
    darwin_dir = get_darwin_user_dir()
    if darwin_dir:
        legacy_path = darwin_dir / "com.apple.notificationcenter" / "db2" / "db"
        if legacy_path.exists():
            return legacy_path

    return None


class NotificationDatabaseDetector(BaseDetector):
    """
    Detector that reads from macOS notification database.

    Extracts actual sender name and message content from Slack notifications.
    Requires Full Disk Access permission.
    """

    def __init__(
        self,
        callback: Callable[[str, str, Optional[dict]], None],
        shutdown_event: Event,
        poll_interval: float = 2.0,
    ):
        """
        Initialize the database detector.

        Args:
            callback: Function to call with (sender, message, metadata).
            shutdown_event: Event to signal shutdown.
            poll_interval: Seconds between database polls.
        """
        super().__init__(callback, shutdown_event)
        self.poll_interval = poll_interval
        self._db_path: Optional[Path] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_timestamp: float = 0
        self._seen_uuids: Set[bytes] = set()

    @property
    def name(self) -> str:
        return "NotificationDatabaseDetector"

    def start(self) -> None:
        """Start polling the notification database."""
        self._db_path = find_notification_database()

        if not self._db_path:
            logger.error(
                "Could not find notification database. "
                "You may need to grant Full Disk Access to Terminal/Python. "
                "Go to: System Settings > Privacy & Security > Full Disk Access"
            )
            return

        logger.info(f"Found notification database: {self._db_path}")

        # Initialize timestamp to now (only get new notifications)
        # Use time.time() for Unix timestamp, subtract MAC_EPOCH_OFFSET for Mac absolute time
        self._last_timestamp = time.time() - MAC_EPOCH_OFFSET

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(f"Started {self.name}")

    def _poll_loop(self) -> None:
        """Poll the database for new notifications."""
        while self._running and not self.shutdown_event.is_set():
            try:
                self._check_for_notifications()
            except sqlite3.OperationalError as e:
                if "unable to open database" in str(e).lower():
                    logger.error(
                        "Cannot access notification database. "
                        "Grant Full Disk Access: System Settings > Privacy & Security > Full Disk Access"
                    )
                    self._running = False
                    break
                else:
                    logger.error(f"Database error: {e}")
            except Exception as e:
                logger.error(f"Error polling database: {e}", exc_info=True)

            self.shutdown_event.wait(timeout=self.poll_interval)

    def _check_for_notifications(self) -> None:
        """Check for new Slack notifications."""
        if not self._db_path:
            return

        try:
            # Open read-only connection
            uri = f"file:{self._db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row

            try:
                cursor = conn.execute(
                    """
                    SELECT
                        record.uuid,
                        record.data,
                        record.delivered_date
                    FROM record
                    INNER JOIN app ON app.app_id = record.app_id
                    WHERE app.identifier = ?
                      AND record.delivered_date > ?
                    ORDER BY record.delivered_date DESC
                    LIMIT 10
                    """,
                    (SLACK_BUNDLE_ID, self._last_timestamp),
                )

                for row in cursor:
                    uuid = row["uuid"]

                    # Skip if already seen
                    if uuid in self._seen_uuids:
                        continue

                    self._seen_uuids.add(uuid)

                    # Update timestamp
                    delivered = row["delivered_date"]
                    if delivered > self._last_timestamp:
                        self._last_timestamp = delivered

                    # Parse notification data
                    sender, message = self._parse_notification(row["data"])

                    if sender and message:
                        logger.info(f"Slack notification: {sender}: {message[:50]}...")
                        self.callback(
                            sender,
                            message,
                            {"source": "database", "uuid": uuid.hex()},
                        )

                # Limit seen UUIDs cache size
                if len(self._seen_uuids) > 1000:
                    self._seen_uuids = set(list(self._seen_uuids)[-500:])

            finally:
                conn.close()

        except Exception as e:
            raise

    def _parse_notification(self, data: bytes) -> tuple[str, str]:
        """Parse notification plist data to extract sender and message."""
        try:
            plist = plistlib.loads(data)
        except Exception as e:
            logger.debug(f"Failed to parse plist: {e}")
            return "", ""

        # Modern format (macOS 10.13+)
        req = plist.get("req", {})

        title = self._clean_string(req.get("titl", ""))
        subtitle = self._clean_string(req.get("subt", ""))
        body = self._clean_string(req.get("body", ""))

        # Slack notification formats:
        # - DM: title=workspace, subtitle=sender, body=message
        # - Channel: title="Sender in #channel", subtitle=workspace, body=message
        if " in #" in title:
            # Channel message: "Sender in #channel"
            sender = title.split(" in #")[0].strip()
        elif subtitle:
            # DM: subtitle is the sender name
            sender = subtitle
        else:
            sender = title

        # Body is the message
        message = body

        # Fallback to legacy format if empty
        if not sender and not message:
            sender, message = self._parse_legacy_format(plist)

        return sender, message

    def _parse_legacy_format(self, plist: dict) -> tuple[str, str]:
        """Parse legacy NSKeyedArchiver format."""
        try:
            objects = plist.get("$objects", [])
            if len(objects) < 2:
                return "", ""

            refs = objects[1]

            title_idx = refs.get("NSTitle", -1)
            body_idx = refs.get("NSInformativetext", -1)

            title = self._clean_string(objects[title_idx]) if title_idx >= 0 else ""
            body = self._clean_string(objects[body_idx]) if body_idx >= 0 else ""

            return title, body
        except Exception:
            return "", ""

    def _clean_string(self, value) -> str:
        """Clean a value to a string."""
        if value is None:
            return ""
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return ""
        s = str(value)
        return s.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()

    def stop(self) -> None:
        """Stop the detector."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info(f"Stopped {self.name}")
