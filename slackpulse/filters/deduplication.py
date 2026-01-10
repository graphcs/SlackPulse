"""Notification deduplication with time-based expiration."""

import hashlib
import time
import logging
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)


class DeduplicationCache:
    """
    Time-based deduplication cache.

    Tracks seen notifications by content hash and expires entries
    after a configurable window.
    """

    def __init__(self, window_seconds: int = 30):
        """
        Initialize the deduplication cache.

        Args:
            window_seconds: Time window for deduplication (default 30s).
        """
        self.window_seconds = window_seconds
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._lock = Lock()

    def _compute_hash(self, sender: str, message: str) -> str:
        """Compute content hash for deduplication."""
        content = f"{sender.lower().strip()}:{message.lower().strip()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _cleanup_expired(self) -> None:
        """Remove expired entries from cache."""
        current_time = time.time()
        cutoff = current_time - self.window_seconds

        # Remove entries older than window
        # OrderedDict maintains insertion order, so we can iterate from oldest
        expired_keys = []
        for key, timestamp in self._cache.items():
            if timestamp < cutoff:
                expired_keys.append(key)
            else:
                break  # All subsequent entries are newer

        for key in expired_keys:
            del self._cache[key]

    def is_duplicate(self, sender: str, message: str) -> bool:
        """
        Check if this notification is a duplicate.

        Returns True if we've seen the same sender+message within the window.
        Also adds the notification to the cache if not a duplicate.

        Args:
            sender: The message sender.
            message: The message content.

        Returns:
            True if duplicate, False if new.
        """
        with self._lock:
            self._cleanup_expired()

            content_hash = self._compute_hash(sender, message)
            current_time = time.time()

            if content_hash in self._cache:
                logger.debug(f"Duplicate notification detected: {sender}")
                return True

            # Add to cache
            self._cache[content_hash] = current_time
            return False

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        """Return number of entries in cache."""
        with self._lock:
            return len(self._cache)
