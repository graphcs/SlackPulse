"""Graceful shutdown signal handling."""

import signal
import logging
from threading import Event

logger = logging.getLogger(__name__)


def install_signal_handlers() -> Event:
    """
    Install handlers for SIGINT and SIGTERM.

    Returns:
        Event that will be set when shutdown is requested.
    """
    shutdown_event = Event()

    def handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    logger.debug("Signal handlers installed for SIGINT and SIGTERM")
    return shutdown_event
