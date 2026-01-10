"""Bot message detection and filtering."""

import re
import logging
from typing import List, Set

logger = logging.getLogger(__name__)


class BotFilter:
    """Detect and filter bot/automated messages."""

    # Default patterns for bot sender names (case-insensitive)
    DEFAULT_BOT_PATTERNS = [
        r"\bbot\b",
        r"slackbot",
        r"workflow",
        r"automation",
        r"\bapp\b",
        r"integration",
        r"webhook",
    ]

    # Default keywords indicating automated messages (in message body)
    DEFAULT_BOT_KEYWORDS = [
        "has joined the channel",
        "has left the channel",
        "set the channel topic",
        "set the channel description",
        "set the channel purpose",
        "was added to",
        "was removed from",
        "archived the channel",
        "unarchived the channel",
        "renamed the channel",
    ]

    def __init__(
        self,
        bot_patterns: List[str] = None,
        bot_keywords: List[str] = None,
    ):
        """
        Initialize the bot filter.

        Args:
            bot_patterns: Regex patterns for bot sender names.
            bot_keywords: Substrings that indicate automated messages.
        """
        patterns = bot_patterns or self.DEFAULT_BOT_PATTERNS
        self._bot_name_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in patterns
        ]
        self._bot_keywords = [
            kw.lower() for kw in (bot_keywords or self.DEFAULT_BOT_KEYWORDS)
        ]

    def is_bot_message(self, sender: str, message: str) -> bool:
        """
        Determine if message is from a bot or automation.

        Args:
            sender: The sender's name.
            message: The message content.

        Returns:
            True if this appears to be a bot/automated message.
        """
        sender_lower = sender.lower()
        message_lower = message.lower()

        # Check sender name against bot patterns
        for pattern in self._bot_name_patterns:
            if pattern.search(sender_lower):
                logger.debug(f"Bot detected by name pattern: {sender}")
                return True

        # Check message body for automation keywords
        for keyword in self._bot_keywords:
            if keyword in message_lower:
                logger.debug(f"Bot detected by keyword: {keyword}")
                return True

        return False

    def add_bot_pattern(self, pattern: str) -> None:
        """Add a new bot name pattern."""
        self._bot_name_patterns.append(re.compile(pattern, re.IGNORECASE))

    def add_bot_keyword(self, keyword: str) -> None:
        """Add a new bot keyword."""
        self._bot_keywords.append(keyword.lower())
