"""Hybrid detector combining filesystem monitoring with database lookups."""

import logging
import sqlite3
import plistlib
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Set
from threading import Event, Lock

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .base import BaseDetector

logger = logging.getLogger(__name__)

MAC_EPOCH_OFFSET = 978307200
SLACK_BUNDLE_ID = "com.tinyspeck.slackmacgap"


def find_notification_database() -> Optional[Path]:
    """Find the notification database path."""
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
    try:
        result = subprocess.run(
            ["getconf", "DARWIN_USER_DIR"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            darwin_dir = Path(result.stdout.strip())
            legacy_path = darwin_dir / "com.apple.notificationcenter" / "db2" / "db"
            if legacy_path.exists():
                return legacy_path
    except Exception:
        pass

    return None


class SlackActivityHandler(FileSystemEventHandler):
    """Handle file system events in Slack's data directory."""

    ACTIVITY_PATTERNS = {"Local Storage", "leveldb", "IndexedDB"}
    IGNORE_PATTERNS = {"GPUCache", "Code Cache", "blob_storage", "Session Storage", ".tmp"}

    def __init__(self, callback: Callable[[], None], debounce_seconds: float = 1.5):
        super().__init__()
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._last_callback_time: float = 0
        self._lock = Lock()

    def _should_trigger(self, path: str) -> bool:
        for pattern in self.IGNORE_PATTERNS:
            if pattern in path:
                return False
        for pattern in self.ACTIVITY_PATTERNS:
            if pattern in path:
                return True
        return False

    def _trigger(self) -> None:
        with self._lock:
            now = time.time()
            if now - self._last_callback_time >= self._debounce_seconds:
                self._last_callback_time = now
                try:
                    self._callback()
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._should_trigger(event.src_path):
            logger.debug(f"Slack activity: {event.src_path}")
            self._trigger()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._should_trigger(event.src_path):
            logger.debug(f"Slack file created: {event.src_path}")
            self._trigger()


class HybridDetector(BaseDetector):
    """
    Hybrid detector: filesystem monitoring + database lookups.

    - Monitors Slack's data directory for file changes
    - When activity detected, checks notification database for new messages
    - Speaks actual message content if available
    - Falls back to "New Slack activity" if no notification found
    """

    SLACK_PATH = Path.home() / "Library" / "Application Support" / "Slack"

    def __init__(
        self,
        callback: Callable[[str, str, Optional[dict]], None],
        shutdown_event: Event,
        debounce_seconds: float = 1.5,
    ):
        super().__init__(callback, shutdown_event)
        self.debounce_seconds = debounce_seconds
        self._db_path = find_notification_database()
        self._observer: Optional[Observer] = None
        self._seen_uuids: Set[bytes] = set()
        self._last_db_check: float = 0
        self._lock = Lock()

    @property
    def name(self) -> str:
        return "HybridDetector"

    def _on_slack_activity(self) -> None:
        """Called when filesystem activity detected."""
        # Check database for new notifications
        notification = self._get_latest_notification()

        if notification:
            sender, message = notification
            logger.info(f"New notification: {sender}: {message[:50]}...")
            self.callback(sender, message, {"source": "hybrid-database"})
        else:
            # No new notification in database - might be self-DM or other activity
            logger.info("Slack activity detected (no new notification in database)")
            self.callback("Slack", "New activity detected", {"source": "hybrid-filesystem"})

    def _get_latest_notification(self) -> Optional[tuple[str, str]]:
        """Check database for new Slack notifications."""
        if not self._db_path:
            return None

        with self._lock:
            try:
                uri = f"file:{self._db_path}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=5.0)
                conn.row_factory = sqlite3.Row

                # Get recent notifications (last 30 seconds)
                cutoff = datetime.utcnow().timestamp() - MAC_EPOCH_OFFSET - 30

                cursor = conn.execute(
                    """
                    SELECT record.uuid, record.data, record.delivered_date
                    FROM record
                    INNER JOIN app ON app.app_id = record.app_id
                    WHERE app.identifier = ?
                      AND record.delivered_date > ?
                    ORDER BY record.delivered_date DESC
                    LIMIT 5
                    """,
                    (SLACK_BUNDLE_ID, cutoff),
                )

                for row in cursor:
                    uuid = row["uuid"]
                    if uuid in self._seen_uuids:
                        continue

                    self._seen_uuids.add(uuid)

                    # Parse notification
                    try:
                        plist = plistlib.loads(row["data"])
                        req = plist.get("req", {})
                        title = str(req.get("titl", ""))
                        body = str(req.get("body", ""))

                        if title and body:
                            sender = title.split(" in #")[0] if " in #" in title else title
                            conn.close()
                            return (sender, body)
                    except Exception as e:
                        logger.debug(f"Parse error: {e}")

                conn.close()

                # Limit cache size
                if len(self._seen_uuids) > 500:
                    self._seen_uuids = set(list(self._seen_uuids)[-250:])

            except sqlite3.OperationalError as e:
                if "unable to open" in str(e).lower():
                    logger.warning("Cannot access notification database")
                else:
                    logger.error(f"Database error: {e}")
            except Exception as e:
                logger.error(f"Error checking database: {e}")

        return None

    def start(self) -> None:
        """Start the hybrid detector."""
        if not self.SLACK_PATH.exists():
            logger.warning(f"Slack directory not found: {self.SLACK_PATH}")
            return

        if self._db_path:
            logger.info(f"Database available: {self._db_path}")
        else:
            logger.warning("Notification database not found - will only detect activity")

        handler = SlackActivityHandler(
            callback=self._on_slack_activity,
            debounce_seconds=self.debounce_seconds,
        )

        self._observer = Observer()
        self._observer.schedule(handler, str(self.SLACK_PATH), recursive=True)
        self._observer.start()
        logger.info(f"Started {self.name} watching: {self.SLACK_PATH}")

    def stop(self) -> None:
        """Stop the detector."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        logger.info(f"Stopped {self.name}")
