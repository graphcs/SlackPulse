# SlackPulse

macOS utility that monitors Slack notifications and reads them aloud using text-to-speech, with optional WhatsApp notifications.

## Quick Start

```bash
git clone https://github.com/graphcs/SlackPulse.git
cd SlackPulse
python3 -m venv .venv && source .venv/bin/activate && pip install -e . && python -m slackpulse
```

**Note:** Requires Full Disk Access for Terminal/Python. Grant it in: System Settings > Privacy & Security > Full Disk Access

## Features

- Reads Slack messages aloud (sender name + message content)
- Sends WhatsApp notifications via Twilio (optional)
- Filters out bot messages and duplicates
- Works with Slack desktop app

## Requirements

- macOS 10.14+
- Python 3.9+
- Slack desktop app
- Full Disk Access permission
- Twilio account (optional, for WhatsApp)

## Usage

```bash
source .venv/bin/activate
python -m slackpulse

# With verbose logging
python -m slackpulse --verbose

# Test WhatsApp setup
python -m slackpulse --sms-test
```

## Configuration

Create `~/.config/slackpulse/config.toml`:

```toml
[tts]
voice = "Samantha"
rate = 150
enabled = true

[filters]
dedup_window_seconds = 30

[sms]
enabled = true
account_sid = "ACxxxxxxxxxx"
auth_token = "xxxxxxxxxx"
from_number = "+1234567890"
to_number = "+0987654321"
use_whatsapp = true
```

## WhatsApp Setup (Twilio)

1. **Create Twilio account** at https://twilio.com (free trial available)

2. **Get credentials** from https://console.twilio.com/:
   - Account SID (starts with `AC`)
   - Auth Token (click eye icon to reveal)

3. **Join WhatsApp Sandbox**:
   - Go to: Twilio Console > Messaging > Try it out > Send a WhatsApp message
   - Send the join code (e.g., "join <word>-<word>") from your phone to the Twilio sandbox number
   - This links your WhatsApp to receive messages

4. **Add to config**:
   ```toml
   [sms]
   enabled = true
   account_sid = "ACxxxx"
   auth_token = "xxxx"
   to_number = "+12025551234"  # Your phone number
   use_whatsapp = true
   ```

5. **Test**: `python -m slackpulse --sms-test`

**Note:** WhatsApp is recommended over SMS because SMS requires A2P 10DLC registration in the US.

## License

MIT
