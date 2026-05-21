# Security Camera Configuration
# Secrets are loaded from .env file to prevent accidental commits
import os

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                try:
                    key, value = line.strip().split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"\'')
                except ValueError:
                    pass

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Paths (change if you move the script)
BASE_DIR = r"C:\security\script"
PHOTOS_DIR = r"C:\security\script\photos"
LOG_FILE = r"C:\security\script\photo_log.txt"

# AI Model Paths
FACE_DETECTION_MODEL = r"C:\security\script\face_detection_yunet_2023mar.onnx"
FACE_RECOGNITION_MODEL = r"C:\security\script\face_recognition_sface_2021dec.onnx"
OWNER_EMBEDDING_FILE = r"C:\security\script\owner_embedding_sface.npy"

# Detection Settings
RECOGNITION_THRESHOLD = 0.30  # Cosine similarity threshold (LOWERED to reduce false positives)
DETECTION_CONFIDENCE = 0.7    # YuNet face detection confidence (LOWERED for better detection)
MAX_CAPTURE_DURATION = 300    # Max seconds to run capture loop (5 minutes)
RETRY_DELAY = 20              # Seconds to wait before retry if no face found
PHOTO_RETENTION_DAYS = 30     # Days to keep photos before cleanup

# Log Settings
MAX_LOG_LINES = 1000          # Maximum lines to keep in log file

# =============================================================================
# BATTERY-AWARE SETTINGS
# =============================================================================
BATTERY_SAVER_ENABLED = True          # Enable battery-aware mode
BATTERY_LOW_THRESHOLD = 30            # Below this %, use minimal mode
BATTERY_MEDIUM_THRESHOLD = 60         # Below this %, use reduced mode

# Detection Resolution (smaller = faster, uses less battery)
# Face detection runs at this resolution, photos saved at full resolution
DETECTION_RESOLUTION = (640, 480)     # Fast detection resolution

# When on BATTERY (unplugged):
BATTERY_MODE_RETRY_DELAY = 30         # Longer delay between retries (saves power)
BATTERY_MODE_BURST_COUNT = 2          # Fewer photos per burst
BATTERY_MODE_RESOLUTION = (1280, 720) # Lower save resolution on battery

# When PLUGGED IN:
PLUGGED_MODE_RETRY_DELAY = 20         # Normal delay
PLUGGED_MODE_BURST_COUNT = 3          # Normal burst
PLUGGED_MODE_RESOLUTION = (1920, 1080) # Full HD when plugged in

# When BATTERY LOW (<30%):
LOW_BATTERY_SKIP_CAPTURE = False      # Set True to skip capture entirely on low battery

# =============================================================================
# ADVANCED RECOGNITION SETTINGS
# =============================================================================
MULTI_SAMPLE_VERIFICATION = True      # Take multiple samples for better accuracy
VERIFICATION_SAMPLES = 3              # Number of face samples to average
MIN_CONFIDENCE_VOTES = 2              # Minimum votes needed to confirm identity
FACE_QUALITY_THRESHOLD = 0.4          # Minimum face detection score (LOWERED)

# =============================================================================
# ACTIVITY MONITOR SETTINGS (Runs when authentication fails)
# =============================================================================
ACTIVITY_MONITOR_ENABLED = True       # Enable activity monitoring on auth failure
ACTIVITY_MONITOR_DURATION = 1800      # Monitoring duration in seconds (30 minutes)
ACTIVITY_LOG_INTERVAL = 2             # Check activity every N seconds
ACTIVITY_NOTIFY_DELAY = 180           # Send notification after N seconds (3 min = 180)
ACTIVITY_NOTIFY_TITLE = "Minecraft"   # Disguised notification title
ACTIVITY_NOTIFY_MESSAGE = "Background sync active. Run stop_monitor.bat to cancel."
