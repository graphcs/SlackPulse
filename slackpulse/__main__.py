"""CLI entry point for SlackPulse."""

import argparse
import sys
from pathlib import Path

from .config import load_config, get_default_config_toml
from .core.monitor import NotificationMonitor
from .utils.logging import setup_logging
from .utils.signals import install_signal_handlers
from .tts.speaker import Speaker
from .sms.sender import TwilioSender


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="slackpulse",
        description="Monitor Slack notifications and read them aloud",
    )

    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path.home() / ".config" / "slackpulse" / "config.toml",
        help="Path to configuration file",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print notifications without TTS",
    )

    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discovery mode: log all distributed notifications",
    )

    parser.add_argument(
        "--database",
        action="store_true",
        help="Use notification database to read actual message content (requires Full Disk Access)",
    )

    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available TTS voices and exit",
    )

    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show default configuration and exit",
    )

    parser.add_argument(
        "--sms-test",
        action="store_true",
        help="Send a test SMS and exit (requires SMS config)",
    )

    args = parser.parse_args()

    # Handle special modes
    if args.list_voices:
        voices = Speaker.list_voices()
        print("Available voices:")
        for voice in voices:
            print(f"  {voice}")
        return 0

    if args.show_config:
        print(get_default_config_toml())
        return 0

    # Load config
    config = load_config(args.config)

    # Handle SMS/WhatsApp test
    if args.sms_test:
        if not config.sms.enabled:
            print("SMS/WhatsApp is not enabled. Add [sms] section to config file.")
            print(f"Config path: {args.config}")
            return 1
        sender = TwilioSender(
            account_sid=config.sms.account_sid,
            auth_token=config.sms.auth_token,
            from_number=config.sms.from_number,
            to_number=config.sms.to_number,
            enabled=True,
            use_whatsapp=config.sms.use_whatsapp,
        )
        msg_type = "WhatsApp" if config.sms.use_whatsapp else "SMS"
        if sender.send_test():
            print(f"Test {msg_type} sent successfully!")
            return 0
        else:
            print(f"Failed to send test {msg_type}. Check your credentials.")
            return 1

    # Setup logging
    setup_logging(
        verbose=args.verbose or args.discover,
        log_file=config.log_file,
    )

    # Install signal handlers
    shutdown_event = install_signal_handlers()

    # Create and run monitor
    monitor = NotificationMonitor(
        shutdown_event=shutdown_event,
        discovery_mode=args.discover,
        dry_run=args.dry_run,
        use_filesystem_fallback=config.monitor.use_filesystem_fallback,
        use_database=args.database,
        tts_voice=config.tts.voice,
        tts_rate=config.tts.rate,
        tts_enabled=config.tts.enabled,
        dedup_window=config.filters.dedup_window_seconds,
        sms_enabled=config.sms.enabled,
        sms_account_sid=config.sms.account_sid,
        sms_auth_token=config.sms.auth_token,
        sms_from_number=config.sms.from_number,
        sms_to_number=config.sms.to_number,
        sms_use_whatsapp=config.sms.use_whatsapp,
    )

    try:
        monitor.run()
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
