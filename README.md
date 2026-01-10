# SlackPulse

macOS utility that monitors Slack notifications and reads them aloud using text-to-speech.

## Quick Start

```bash
# Clone and run
git clone https://github.com/graphcs/SlackPulse.git
cd SlackPulse
python3 -m venv .venv && source .venv/bin/activate && pip install -e . && python -m slackpulse
```

**Note:** Requires Full Disk Access for Terminal/Python. Grant it in: System Settings > Privacy & Security > Full Disk Access

## Features

- Reads Slack messages aloud (sender name + message content)
- Filters out bot messages and duplicates
- Works with Slack desktop app

## Requirements

- macOS 10.14+
- Python 3.9+
- Slack desktop app
- Full Disk Access permission

## Usage

```bash
# Activate venv (if not already)
source .venv/bin/activate

# Run SlackPulse
python -m slackpulse

# Run with verbose logging
python -m slackpulse --verbose

# Dry run (print instead of speak)
python -m slackpulse --dry-run

# List available TTS voices
python -m slackpulse --list-voices
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
```

