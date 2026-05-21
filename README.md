# Security Camera System

A smart security camera that captures photos on Windows login with face detection and recognition.

## Features

- **Face Detection** (YuNet AI model)
- **Face Recognition** (SFace AI model) - distinguishes owner from intruders
- **Telegram Alerts** - instant notifications for intruders/suspicious activity
- **Battery-Aware Mode** - reduces power consumption on laptops
- **Web Dashboard** - view all captures in a modern UI

## Prerequisites

Install required Python packages:
```powershell
pip install opencv-python numpy psutil requests
```

## Setup

### Task Scheduler (Recommended)

1. Open "Task Scheduler" from Start menu
2. Click "Import Task" and select `task_config.xml`
3. Or manually create a task triggered "When I log on" that runs:
   ```
   pythonw.exe "C:\path\to\script\capture_photo.py"
   ```

### Register Your Face

Run this once to register yourself as the owner:
```powershell
python register_owner.py
```

## Configuration

1. Create a `.env` file in the script directory and add your Telegram credentials:
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

2. Edit `config.py` to customize:
   - Detection thresholds
   - Battery settings
   - Photo retention period

## Files

| File | Purpose |
|------|---------|
| `capture_photo.py` | Main security camera script |
| `config.py` | All configuration settings |
| `register_owner.py` | Register your face as owner |
| `photos/view_photos.html` | Security dashboard |

## Where are the photos?

Photos are saved in the `photos` folder within the script directory.

Open `photos/view_photos.html` in a browser to view the dashboard.
