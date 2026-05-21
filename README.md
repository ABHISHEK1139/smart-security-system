# Security Camera System

A smart security camera that captures photos on Windows login with face detection and recognition.

## Features

- **Face Detection** (YuNet AI model)
- **Face Recognition** (SFace AI model) - distinguishes owner from intruders
- **Telegram Alerts** - instant notifications for intruders/suspicious activity
- **Battery-Aware Mode** - reduces power consumption on laptops
- **Web Dashboard** - view all captures in a modern UI

## Prerequisites

Ensure you have Python installed. Then, install the required packages:
```powershell
pip install opencv-python numpy psutil requests python-dotenv
```

## Setup & Configuration

### 1. Protect Your Secrets
Create a `.env` file in the script directory and add your Telegram credentials:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```
*(This file is ignored by Git to protect your secrets).*

### 2. Configure Settings
Edit `config.py` to customize:
- Detection thresholds
- Battery settings
- Photo retention period

### 3. Register Your Face
Run this once to register yourself as the owner:
```powershell
python register_owner.py
```
*(Look into the camera until it confirms your face is registered).*

## How to Use

**Option A: Manual Run (For testing)**
Simply run the main script whenever you want to start monitoring:
```powershell
python capture_photo.py
```

**Option B: Background Automation (Recommended)**
To have the script run completely invisibly every time you log into your Windows PC:
1. Open **Task Scheduler** from the Windows Start menu.
2. Click **Import Task** and select `task_config.xml`.
   *(Note: If you moved your folder, you will need to edit `task_config.xml` first to ensure the `<Command>` and `<Arguments>` paths match exactly where your script lives).*
3. The system will now automatically run silently in the background every time you unlock your PC!

## Where are the photos?

Photos are saved in the `photos` folder within the script directory.

Open `photos/view_photos.html` in a browser to view the offline security dashboard.

## Files

| File | Purpose |
|------|---------|
| `capture_photo.py` | Main security camera script |
| `config.py` | All configuration settings |
| `register_owner.py` | Register your face as owner |
| `photos/view_photos.html` | Security dashboard |
