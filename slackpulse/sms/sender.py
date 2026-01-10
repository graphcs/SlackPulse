"""SMS/WhatsApp sender using Twilio API."""

import logging

logger = logging.getLogger(__name__)

# Twilio WhatsApp sandbox number
WHATSAPP_SANDBOX_NUMBER = "+14155238886"


class TwilioSender:
    """
    SMS/WhatsApp sender using Twilio API.

    Sends notifications for Slack messages via SMS or WhatsApp.
    """

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
        to_number: str = "",
        enabled: bool = False,
        use_whatsapp: bool = False,
    ):
        """
        Initialize the Twilio sender.

        Args:
            account_sid: Twilio Account SID.
            auth_token: Twilio Auth Token.
            from_number: Twilio phone number to send from (ignored for WhatsApp sandbox).
            to_number: Phone number to send to.
            enabled: Whether messaging is enabled.
            use_whatsapp: Use WhatsApp instead of SMS (recommended, no A2P registration needed).
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_number = to_number
        self.enabled = enabled
        self.use_whatsapp = use_whatsapp
        self._client = None

        if self.enabled and self._has_credentials():
            self._init_client()

    def _has_credentials(self) -> bool:
        """Check if all required credentials are present."""
        return bool(
            self.account_sid
            and self.auth_token
            and self.from_number
            and self.to_number
        )

    def _init_client(self) -> None:
        """Initialize the Twilio client."""
        try:
            from twilio.rest import Client

            self._client = Client(self.account_sid, self.auth_token)
            logger.info("Twilio SMS client initialized")
        except ImportError:
            logger.error("twilio package not installed. Run: pip install twilio")
            self.enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
            self.enabled = False

    def send(self, text: str) -> bool:
        """
        Send a message via SMS or WhatsApp.

        Args:
            text: Message text to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled:
            logger.debug(f"Messaging disabled, would send: {text}")
            return False

        if not self._client:
            logger.warning("Twilio client not initialized")
            return False

        # Truncate message
        max_len = 1600
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."

        try:
            if self.use_whatsapp:
                # WhatsApp: use sandbox number and prefix with whatsapp:
                from_addr = f"whatsapp:{WHATSAPP_SANDBOX_NUMBER}"
                to_addr = f"whatsapp:{self.to_number}"
                msg_type = "WhatsApp"
            else:
                # SMS: use configured numbers
                from_addr = self.from_number
                to_addr = self.to_number
                msg_type = "SMS"

            message = self._client.messages.create(
                body=text,
                from_=from_addr,
                to=to_addr,
            )
            logger.debug(f"{msg_type} sent: {message.sid}")
            return True
        except Exception as e:
            logger.error(f"Failed to send {msg_type}: {e}")
            return False

    def send_notification(self, sender: str, message: str) -> bool:
        """
        Send a notification as SMS.

        Args:
            sender: Message sender name.
            message: Message content.

        Returns:
            True if sent successfully, False otherwise.
        """
        # Truncate message for SMS
        max_message_len = 140
        if len(message) > max_message_len:
            message = message[:max_message_len] + "..."

        text = f"Slack from {sender}: {message}"
        return self.send(text)

    def send_test(self) -> bool:
        """
        Send a test SMS message.

        Returns:
            True if sent successfully, False otherwise.
        """
        return self.send("SlackPulse test message - SMS notifications are working!")
