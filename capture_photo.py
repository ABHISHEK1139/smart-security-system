import cv2
import datetime
import os
import time
import psutil
import socket
import urllib.request
import subprocess
import re
import ctypes
import winsound # For alarm
import requests # For Telegram
import numpy as np

# Import Activity Monitor for failed authentication
try:
    from activity_monitor import run_detached as start_activity_monitor
    ACTIVITY_MONITOR_AVAILABLE = True
except ImportError:
    ACTIVITY_MONITOR_AVAILABLE = False
    print("Warning: activity_monitor.py not found. Activity logging disabled.")

# Import configuration (keeps sensitive data separate)
try:
    from config import (
        TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
        BASE_DIR, PHOTOS_DIR, LOG_FILE,
        FACE_DETECTION_MODEL, FACE_RECOGNITION_MODEL, OWNER_EMBEDDING_FILE,
        RECOGNITION_THRESHOLD, DETECTION_CONFIDENCE, MAX_CAPTURE_DURATION,
        RETRY_DELAY, PHOTO_RETENTION_DAYS, MAX_LOG_LINES,
        # Battery-aware settings
        BATTERY_SAVER_ENABLED, BATTERY_LOW_THRESHOLD, BATTERY_MEDIUM_THRESHOLD,
        BATTERY_MODE_RETRY_DELAY, BATTERY_MODE_BURST_COUNT, BATTERY_MODE_RESOLUTION,
        PLUGGED_MODE_RETRY_DELAY, PLUGGED_MODE_BURST_COUNT, PLUGGED_MODE_RESOLUTION,
        LOW_BATTERY_SKIP_CAPTURE, DETECTION_RESOLUTION,
        # Advanced recognition settings
        MULTI_SAMPLE_VERIFICATION, VERIFICATION_SAMPLES, MIN_CONFIDENCE_VOTES,
        FACE_QUALITY_THRESHOLD
    )
except ImportError:
    # Fallback defaults if config.py is missing
    TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
    TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
    BASE_DIR = r"C:\security\script"
    PHOTOS_DIR = r"C:\security\script\photos"
    LOG_FILE = r"C:\security\script\photo_log.txt"
    FACE_DETECTION_MODEL = r"C:\security\script\face_detection_yunet_2023mar.onnx"
    FACE_RECOGNITION_MODEL = r"C:\security\script\face_recognition_sface_2021dec.onnx"
    OWNER_EMBEDDING_FILE = r"C:\security\script\owner_embedding_sface.npy"
    RECOGNITION_THRESHOLD = 0.35
    DETECTION_CONFIDENCE = 0.8
    MAX_CAPTURE_DURATION = 300
    RETRY_DELAY = 20
    PHOTO_RETENTION_DAYS = 30
    MAX_LOG_LINES = 1000
    # Battery defaults
    BATTERY_SAVER_ENABLED = True
    BATTERY_LOW_THRESHOLD = 30
    BATTERY_MEDIUM_THRESHOLD = 60
    BATTERY_MODE_RETRY_DELAY = 30
    BATTERY_MODE_BURST_COUNT = 2
    BATTERY_MODE_RESOLUTION = (1280, 720)
    PLUGGED_MODE_RETRY_DELAY = 20
    PLUGGED_MODE_BURST_COUNT = 3
    PLUGGED_MODE_RESOLUTION = (1920, 1080)
    LOW_BATTERY_SKIP_CAPTURE = False
    DETECTION_RESOLUTION = (640, 480)
    # Recognition defaults
    MULTI_SAMPLE_VERIFICATION = True
    VERIFICATION_SAMPLES = 3
    MIN_CONFIDENCE_VOTES = 2
    FACE_QUALITY_THRESHOLD = 0.5


def get_power_status():
    """Get current power status and battery level.
    
    Returns:
        dict: {
            'on_battery': bool,      # True if running on battery
            'percent': int,          # Battery percentage (0-100)
            'power_mode': str,       # 'plugged', 'battery', 'low_battery'
            'should_skip': bool      # True if capture should be skipped
        }
    """
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            # Desktop PC, no battery
            return {
                'on_battery': False,
                'percent': 100,
                'power_mode': 'plugged',
                'should_skip': False
            }
        
        on_battery = not battery.power_plugged
        percent = int(battery.percent)
        
        if not on_battery:
            power_mode = 'plugged'
        elif percent < BATTERY_LOW_THRESHOLD:
            power_mode = 'low_battery'
        else:
            power_mode = 'battery'
        
        should_skip = (power_mode == 'low_battery' and LOW_BATTERY_SKIP_CAPTURE)
        
        return {
            'on_battery': on_battery,
            'percent': percent,
            'power_mode': power_mode,
            'should_skip': should_skip
        }
    except Exception:
        return {
            'on_battery': False,
            'percent': 100,
            'power_mode': 'plugged',
            'should_skip': False
        }


def get_adaptive_settings(power_status):
    """Get capture settings based on power status.
    
    Returns appropriate resolution, burst count, and retry delay based on
    whether the device is plugged in or running on battery.
    """
    if not BATTERY_SAVER_ENABLED or power_status['power_mode'] == 'plugged':
        return {
            'resolution': PLUGGED_MODE_RESOLUTION,
            'burst_count': PLUGGED_MODE_BURST_COUNT,
            'retry_delay': PLUGGED_MODE_RETRY_DELAY
        }
    else:
        return {
            'resolution': BATTERY_MODE_RESOLUTION,
            'burst_count': BATTERY_MODE_BURST_COUNT,
            'retry_delay': BATTERY_MODE_RETRY_DELAY
        }

import json as json_module  # For alert queue

# Offline alert queue file
ALERT_QUEUE_FILE = os.path.join(BASE_DIR, "pending_alerts.json")

# Startup delay to wait for session to be ready (seconds)
STARTUP_DELAY = 3


def is_workstation_locked():
    """Check if the Windows workstation is currently locked (at lock/login screen).
    
    Returns:
        bool: True if locked (at password screen), False if unlocked (desktop visible)
    """
    try:
        user32 = ctypes.windll.user32
        
        # Method 1: Check for LogonUI.exe (Windows lock screen process)
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and proc.info['name'].lower() == 'logonui.exe':
                return True  # Lock screen is active
        
        # Method 2: Check if we can access the interactive desktop
        # GetForegroundWindow returns 0 when locked
        hwnd = user32.GetForegroundWindow()
        if hwnd == 0:
            return True  # No foreground window = likely locked
        
        # Method 3: Check the current input desktop name
        # When locked, the input desktop is "Winlogon", not "Default"
        try:
            hdesk = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
            if hdesk:
                # Get desktop name
                name_buffer = ctypes.create_unicode_buffer(256)
                length = ctypes.c_ulong()
                user32.GetUserObjectInformationW(hdesk, 2, name_buffer, 256 * 2, ctypes.byref(length))
                desktop_name = name_buffer.value.lower()
                user32.CloseDesktop(hdesk)
                
                # If desktop is "winlogon" or "screen-saver", we're locked
                if 'winlogon' in desktop_name or 'screen' in desktop_name:
                    return True
        except:
            pass
        
        return False  # Not locked
        
    except Exception:
        return False  # Assume not locked on error


def wait_for_unlock(timeout=120, log_func=None):
    """Wait until the workstation is unlocked (user has entered password).
    
    Args:
        timeout: Maximum seconds to wait (default 2 minutes)
        log_func: Optional logging function
        
    Returns:
        bool: True if unlocked, False if timed out while still locked
    """
    start = time.time()
    check_interval = 2  # Check every 2 seconds
    
    while (time.time() - start) < timeout:
        if not is_workstation_locked():
            # Double-check after a short delay to ensure stable state
            time.sleep(1)
            if not is_workstation_locked():
                if log_func:
                    log_func(f"Desktop unlocked after {time.time() - start:.1f}s")
                return True
        time.sleep(check_interval)
    
    if log_func:
        log_func(f"Timeout waiting for unlock after {timeout}s")
    return False


def is_session_ready():
    """Check if the Windows desktop session is fully active and ready.
    
    This helps avoid running the script during boot before login,
    when the Task Scheduler fires LogonTrigger prematurely.
    
    Returns:
        bool: True if session is ready, False otherwise
    """
    try:
        # Check 1: Is workstation locked? (Must be unlocked first)
        if is_workstation_locked():
            return False
        
        # Check 2: Is explorer.exe running? (User shell must be loaded)
        explorer_running = False
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and proc.info['name'].lower() == 'explorer.exe':
                explorer_running = True
                break
        
        if not explorer_running:
            return False
        
        # Check 3: Can we get the foreground window? (Desktop must be active)
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        
        return hwnd != 0  # Must have a foreground window
        
    except Exception:
        return False


def wait_for_session_ready(timeout=30, log_func=None):
    """Wait for the Windows session to be fully ready.
    
    Args:
        timeout: Maximum seconds to wait
        log_func: Optional logging function
        
    Returns:
        bool: True if session became ready, False if timed out
    """
    start = time.time()
    while (time.time() - start) < timeout:
        if is_session_ready():
            if log_func:
                log_func(f"Session ready after {time.time() - start:.1f}s")
            return True
        time.sleep(1)
    
    if log_func:
        log_func(f"Session not ready after {timeout}s timeout")
    return False


def queue_alert(status, photo_path, message):
    """Save alert to queue file for later sending when internet is available"""
    try:
        queue = []
        if os.path.exists(ALERT_QUEUE_FILE):
            with open(ALERT_QUEUE_FILE, 'r') as f:
                queue = json_module.load(f)
        
        queue.append({
            "status": status,
            "photo_path": photo_path,
            "message": message,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        with open(ALERT_QUEUE_FILE, 'w') as f:
            json_module.dump(queue, f)
    except Exception:
        pass

def send_queued_alerts():
    """Try to send any queued alerts (call this when internet might be available)"""
    if not os.path.exists(ALERT_QUEUE_FILE):
        return
    
    try:
        with open(ALERT_QUEUE_FILE, 'r') as f:
            queue = json_module.load(f)
        
        if not queue:
            return
        
        # Try to send each queued alert
        remaining = []
        for alert in queue:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                if alert['photo_path'] and os.path.exists(alert['photo_path']):
                    with open(alert['photo_path'], "rb") as f:
                        files = {"photo": f}
                        data = {"chat_id": TELEGRAM_CHAT_ID, "caption": f"[DELAYED] {alert['message']}"}
                        response = requests.post(url, data=data, files=files, timeout=10)
                        if response.status_code != 200:
                            remaining.append(alert)
                else:
                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    data = {"chat_id": TELEGRAM_CHAT_ID, "text": f"[DELAYED] {alert['message']}"}
                    response = requests.post(url, data=data, timeout=10)
                    if response.status_code != 200:
                        remaining.append(alert)
            except Exception:
                remaining.append(alert)  # Keep in queue if failed
        
        # Update queue with remaining alerts
        with open(ALERT_QUEUE_FILE, 'w') as f:
            json_module.dump(remaining, f)
            
    except Exception:
        pass

def send_telegram_alert(status, session_dir):
    if "YOUR_BOT_TOKEN" in TELEGRAM_BOT_TOKEN:
        return # Not configured

    # Build message
    message = f"⚠️ Security Alert: {status}\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    if "INTRUDER" in status:
        message = f"🚨 INTRUDER DETECTED!\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    elif "SPOOKY" in status:
        message = f"👻 SPOOKY: No face detected after 2 attempts!\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    elif "SUSPICIOUS" in status:
        message = f"⚠️ Suspicious Activity (No Face Detected)\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # Find the latest photo to send
    photo_path = None
    try:
        photos = [os.path.join(session_dir, f) for f in os.listdir(session_dir) if f.endswith(".jpg")]
        if photos:
            photo_path = max(photos, key=os.path.getctime)
    except (OSError, IOError):
        pass

    # Try to send Telegram
    try:
        # First, try to send any queued alerts
        send_queued_alerts()
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        if photo_path:
            with open(photo_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": message}
                response = requests.post(url, data=data, files=files, timeout=10)
                if response.status_code != 200:
                    raise Exception("Telegram failed")
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
            response = requests.post(url, data=data, timeout=10)
            if response.status_code != 200:
                raise Exception("Telegram failed")
                
    except Exception as e:
        # No internet - queue the alert for later
        print(f"Telegram Error (queued for later): {e}")
        queue_alert(status, photo_path, message)

def get_system_info():
    info = []
    
    # 1. User & Host
    try:
        user = os.getlogin()
        host = socket.gethostname()
        info.append(f"User: {user} @ {host}")
    except:
        pass

    # 2. Battery
    try:
        battery = psutil.sensors_battery()
        if battery:
            plugged = "Charging" if battery.power_plugged else "Battery"
            info.append(f"Power: {battery.percent}% ({plugged})")
    except:
        pass

    # 3. WiFi SSID (Windows specific)
    try:
        # Run netsh to get wifi info (with hidden window)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        output = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces'], startupinfo=startupinfo).decode('utf-8', errors='ignore')
        # Look for "SSID" or "SSID" (depends on locale, usually "SSID")
        ssid_match = re.search(r'SSID\s*:\s*(.*)', output)
        if ssid_match:
            ssid = ssid_match.group(1).strip()
            info.append(f"WiFi: {ssid}")
    except:
        pass

    # 4. Public IP (with timeout)
    try:
        ip = urllib.request.urlopen('https://api.ipify.org', timeout=2).read().decode('utf8')
        info.append(f"Public IP: {ip}")
    except:
        info.append("Public IP: Offline")

    return info

def generate_daily_report(base_dir):
    import json
    
    # 1. Find all unique dates from folder names
    all_dates = set()
    if os.path.exists(base_dir):
        for d in os.listdir(base_dir):
            if os.path.isdir(os.path.join(base_dir, d)) and d.count("-") >= 2:
                parts = d.split("_")
                if len(parts) >= 1:
                    date_part = parts[0] # 2025-12-06
                    if len(date_part.split("-")) == 3:
                        all_dates.add(date_part)
    
    sorted_dates = sorted(list(all_dates))
    if not sorted_dates:
        return

    # 2. Collect ALL data into a single dictionary
    # Structure: { "2025-12-06": [ {time, status, images...} ], ... }
    all_data = {}
    
    for date_key in sorted_dates:
        sessions = []
        if os.path.exists(base_dir):
            for item in sorted(os.listdir(base_dir), reverse=True): # Newest first
                item_path = os.path.join(base_dir, item)
                if os.path.isdir(item_path) and item.startswith(date_key):
                    parts = item.split("_")
                    if len(parts) >= 3:
                        time_str = parts[1].replace("-", ":")
                        status = "_".join(parts[2:])
                        
                        images = []
                        for img in sorted(os.listdir(item_path), reverse=True):  # Latest photos first
                            if img.endswith(".jpg"):
                                images.append(f"{item}/{img}")
                        
                        if images:
                            sessions.append({
                                "time": time_str,
                                "status": status,
                                "images": images,
                                "is_alert": "SUSPICIOUS" in status or "INTRUDER" in status or "SPOOKY" in status
                            })
        all_data[date_key] = sessions

    # 2.5 Collect Activity Logs
    activity_logs = []
    activity_log_dir = os.path.join(BASE_DIR, "activity_logs")
    if os.path.exists(activity_log_dir):
        for log_file in sorted(os.listdir(activity_log_dir), reverse=True):
            if log_file.endswith('.json'):
                try:
                    log_path = os.path.join(activity_log_dir, log_file)
                    with open(log_path, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                    activity_logs.append({
                        'filename': log_file,
                        'trigger': log_data.get('trigger_reason', 'UNKNOWN'),
                        'start_time': log_data.get('start_time', ''),
                        'end_time': log_data.get('end_time', ''),
                        'system_info': log_data.get('system_info', {}),
                        'summary': log_data.get('summary', {}),
                        'window_activity': log_data.get('window_activity', [])[:50],  # Limit to 50 entries
                        'app_launches': log_data.get('app_launches', []),
                        'false_positive': log_data.get('false_positive', False)
                    })
                except Exception:
                    pass

    # 3. Generate Single Page Application (SPA) HTML
    html_path = os.path.join(base_dir, "view_photos.html")
    
    # Serialize data to JSON for embedding
    json_data = json.dumps(all_data)
    activity_logs_json = json.dumps(activity_logs)
    
    # Get current date (default to latest available)
    latest_date = sorted_dates[-1]
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Security Log</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; margin: 0; padding: 20px; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #333; padding-bottom: 20px; }}
            .stats {{ display: flex; gap: 20px; }}
            .stat-box {{ background: #1e1e1e; padding: 15px 25px; border-radius: 8px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            .stat-num {{ font-size: 28px; font-weight: bold; color: #4CAF50; }}
            .stat-label {{ font-size: 12px; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }}
            
            /* Tab Navigation */
            .tab-bar {{ display: flex; gap: 5px; margin-bottom: 20px; background: #1e1e1e; padding: 5px; border-radius: 8px; }}
            .tab-btn {{ cursor: pointer; color: #aaa; background: transparent; padding: 12px 25px; border-radius: 6px; font-size: 14px; font-weight: bold; transition: all 0.2s; border: none; }}
            .tab-btn:hover {{ background: #333; color: #fff; }}
            .tab-btn.active {{ background: #4CAF50; color: #fff; }}
            .tab-btn.activity-tab.active {{ background: #ff9800; }}
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; }}
            
            /* Navigation Bar */
            .nav-bar {{ display: flex; gap: 10px; margin-bottom: 20px; background: #1e1e1e; padding: 10px; border-radius: 8px; align-items: center; }}
            .nav-btn {{ cursor: pointer; color: #fff; background: #333; padding: 8px 15px; border-radius: 4px; font-size: 14px; transition: background 0.2s; user-select: none; }}
            .nav-btn:hover {{ background: #444; }}
            .nav-btn.disabled {{ opacity: 0.3; pointer-events: none; }}
            .date-display {{ font-weight: bold; font-size: 18px; margin: 0 15px; color: #4CAF50; }}
            select.date-select {{ background: #333; color: #fff; border: none; padding: 8px; border-radius: 4px; cursor: pointer; }}

            .filter-bar {{ margin-bottom: 20px; padding: 10px; background: #1e1e1e; border-radius: 8px; display: flex; gap: 10px; align-items: center; }}
            .filter-btn {{ background: #333; border: none; color: #aaa; padding: 8px 16px; border-radius: 20px; cursor: pointer; transition: all 0.2s; font-weight: bold; }}
            .filter-btn:hover {{ background: #444; color: #fff; }}
            .filter-btn.active {{ background: #4CAF50; color: #fff; }}
            .filter-btn.active.alert-filter {{ background: #ff4444; }}
            
            .timeline-container {{ margin-bottom: 30px; background: #1e1e1e; padding: 20px; border-radius: 10px; }}
            .timeline-bar {{ height: 10px; background: #333; border-radius: 5px; position: relative; margin-top: 10px; }}
            .timeline-marker {{ position: absolute; width: 12px; height: 12px; border-radius: 50%; top: -1px; transform: translateX(-50%); cursor: pointer; transition: transform 0.2s; border: 2px solid #1e1e1e; }}
            .timeline-marker:hover {{ transform: translateX(-50%) scale(1.5); z-index: 10; }}
            .timeline-marker.safe {{ background: #4CAF50; }}
            .timeline-marker.alert {{ background: #ff4444; }}
            .timeline-marker.spooky {{ background: #9C27B0; }}
            .timeline-marker.suspicious {{ background: #FFC107; }}
            .timeline-labels {{ display: flex; justify-content: space-between; margin-top: 5px; color: #666; font-size: 12px; }}

            .session-card {{ background: #1e1e1e; border-radius: 10px; padding: 20px; margin-bottom: 20px; border-left: 5px solid #555; transition: transform 0.2s; }}
            .session-card:hover {{ transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.3); }}
            .session-card.alert {{ border-left-color: #ff4444; background: #2a1a1a; }}
            .session-card.safe {{ border-left-color: #4CAF50; }}
            .session-card.spooky {{ border-left-color: #9C27B0; background: #1a1a2a; }}
            .session-card.suspicious {{ border-left-color: #FFC107; }}
            
            .session-header {{ display: flex; justify-content: space-between; margin-bottom: 15px; align-items: center; }}
            .time-badge {{ font-size: 20px; font-weight: bold; color: #fff; }}
            .status-badge {{ padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; text-transform: uppercase; }}
            .alert .status-badge {{ background: rgba(255, 68, 68, 0.2); color: #ff4444; border: 1px solid #ff4444; }}
            .safe .status-badge {{ background: rgba(76, 175, 80, 0.2); color: #4CAF50; border: 1px solid #4CAF50; }}
            .spooky .status-badge {{ background: rgba(156, 39, 176, 0.2); color: #9C27B0; border: 1px solid #9C27B0; }}
            .suspicious .status-badge {{ background: rgba(255, 193, 7, 0.2); color: #FFC107; border: 1px solid #FFC107; }}
            
            .gallery {{ 
                display: flex; 
                gap: 15px; 
                overflow-x: auto; 
                padding-bottom: 15px;
                scroll-snap-type: x mandatory;
                scrollbar-width: thin;
                scrollbar-color: #444 #1e1e1e;
            }}
            .gallery::-webkit-scrollbar {{ height: 8px; }}
            .gallery::-webkit-scrollbar-track {{ background: #1e1e1e; border-radius: 4px; }}
            .gallery::-webkit-scrollbar-thumb {{ background: #444; border-radius: 4px; }}
            .gallery::-webkit-scrollbar-thumb:hover {{ background: #555; }}
            
            .gallery img {{ 
                height: 200px; 
                border-radius: 8px; 
                cursor: pointer; 
                transition: all 0.2s; 
                border: 2px solid transparent;
                scroll-snap-align: start;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            }}
            .gallery img:hover {{ transform: scale(1.02); border-color: #fff; box-shadow: 0 5px 15px rgba(0,0,0,0.4); }}
            
            /* Lightbox */
            .lightbox {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); justify-content: center; align-items: center; z-index: 1000; backdrop-filter: blur(5px); }}
            .lightbox img {{ max-height: 90vh; max-width: 80vw; border-radius: 4px; box-shadow: 0 0 20px rgba(0,0,0,0.5); }}
            .lightbox:target {{ display: flex; }}
            .close-hint {{ position: absolute; top: 20px; right: 30px; color: #fff; font-size: 30px; cursor: pointer; z-index: 1002; }}
            
            .lb-nav {{ position: absolute; top: 50%; transform: translateY(-50%); color: white; font-size: 40px; cursor: pointer; padding: 20px; background: rgba(0,0,0,0.3); border-radius: 50%; transition: background 0.2s; user-select: none; z-index: 1001; }}
            .lb-nav:hover {{ background: rgba(255,255,255,0.1); }}
            .lb-prev {{ left: 20px; }}
            .lb-next {{ right: 20px; }}
            
            /* Activity Logs Styles */
            .activity-log-card {{ background: #1e1e1e; border-radius: 10px; padding: 20px; margin-bottom: 15px; border-left: 5px solid #ff9800; }}
            .activity-log-card.false-positive {{ border-left-color: #666; opacity: 0.6; }}
            .activity-log-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
            .activity-trigger {{ padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; background: rgba(255, 152, 0, 0.2); color: #ff9800; border: 1px solid #ff9800; }}
            .activity-trigger.intruder {{ background: rgba(255, 68, 68, 0.2); color: #ff4444; border-color: #ff4444; }}
            .activity-trigger.suspicious {{ background: rgba(255, 193, 7, 0.2); color: #FFC107; border-color: #FFC107; }}
            .activity-trigger.false-positive {{ background: rgba(102, 102, 102, 0.2); color: #999; border-color: #666; }}
            .activity-summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 15px; }}
            .activity-stat {{ background: #2a2a2a; padding: 10px; border-radius: 6px; text-align: center; }}
            .activity-stat-num {{ font-size: 20px; font-weight: bold; color: #ff9800; }}
            .activity-stat-label {{ font-size: 11px; color: #888; text-transform: uppercase; }}
            .activity-details {{ max-height: 300px; overflow-y: auto; background: #0d0d0d; border-radius: 6px; padding: 10px; font-family: monospace; font-size: 12px; }}
            .activity-entry {{ padding: 5px 0; border-bottom: 1px solid #222; }}
            .activity-entry:last-child {{ border-bottom: none; }}
            .activity-time {{ color: #4CAF50; margin-right: 10px; }}
            .activity-app {{ color: #2196F3; }}
            .activity-window {{ color: #aaa; }}
            .no-activity {{ text-align: center; color: #666; padding: 40px; }}
        </style>
        <script>
            // EMBEDDED DATA
            const securityData = {json_data};
            const activityLogs = {activity_logs_json};
            const allDates = Object.keys(securityData).sort();
            let currentDate = "{latest_date}";
            let currentFilter = 'all';
            let currentTab = 'photos';
            
            let currentImages = [];
            let currentIndex = 0;

            function init() {{
                renderPage(currentDate);
                renderActivityLogs();
                // Update activity log count in tab
                document.getElementById('activity-count').innerText = activityLogs.length;
            }}
            
            function switchTab(tab) {{
                currentTab = tab;
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                if (tab === 'photos') {{
                    document.getElementById('tab-photos').classList.add('active');
                    document.getElementById('content-photos').classList.add('active');
                }} else {{
                    document.getElementById('tab-activity').classList.add('active');
                    document.getElementById('content-activity').classList.add('active');
                }}
            }}
            
            function renderActivityLogs() {{
                const container = document.getElementById('activity-logs');
                container.innerHTML = '';
                
                if (activityLogs.length === 0) {{
                    container.innerHTML = '<div class="no-activity">📋 No activity logs recorded yet.<br><small>Activity logs are created when authentication fails (INTRUDER/SUSPICIOUS detected)</small></div>';
                    return;
                }}
                
                activityLogs.forEach(log => {{
                    const card = document.createElement('div');
                    card.className = 'activity-log-card' + (log.false_positive ? ' false-positive' : '');
                    
                    let triggerClass = '';
                    if (log.trigger.includes('INTRUDER')) triggerClass = 'intruder';
                    else if (log.trigger.includes('SUSPICIOUS')) triggerClass = 'suspicious';
                    if (log.false_positive) triggerClass = 'false-positive';
                    
                    const summary = log.summary || {{}};
                    const sysInfo = log.system_info || {{}};
                    
                    let windowActivityHtml = '';
                    if (log.window_activity && log.window_activity.length > 0) {{
                        log.window_activity.forEach(w => {{
                            windowActivityHtml += `<div class="activity-entry"><span class="activity-time">${{w.time}}</span><span class="activity-app">${{w.process}}</span> - <span class="activity-window">${{w.window}}</span></div>`;
                        }});
                    }} else {{
                        windowActivityHtml = '<div class="activity-entry" style="color:#666;">No window activity recorded</div>';
                    }}
                    
                    let appLaunchHtml = '';
                    if (log.app_launches && log.app_launches.length > 0) {{
                        log.app_launches.forEach(a => {{
                            appLaunchHtml += `<div class="activity-entry"><span class="activity-time">${{a.time}}</span>🚀 <span class="activity-app">${{a.name}}</span></div>`;
                        }});
                    }}
                    
                    card.innerHTML = `
                        <div class="activity-log-header">
                            <div>
                                <div style="font-size: 18px; font-weight: bold; margin-bottom: 5px;">📋 ${{log.start_time}}</div>
                                <div style="font-size: 12px; color: #666;">Duration: ${{summary.total_duration_minutes || 0}} minutes | User: ${{sysInfo.username || 'N/A'}} | ${{sysInfo.battery || ''}}</div>
                            </div>
                            <span class="activity-trigger ${{triggerClass}}">${{log.false_positive ? '❌ FALSE POSITIVE' : '⚠️ ' + log.trigger}}</span>
                        </div>
                        <div class="activity-summary">
                            <div class="activity-stat">
                                <div class="activity-stat-num">${{summary.window_switches || 0}}</div>
                                <div class="activity-stat-label">Window Switches</div>
                            </div>
                            <div class="activity-stat">
                                <div class="activity-stat-num">${{summary.apps_launched || 0}}</div>
                                <div class="activity-stat-label">Apps Launched</div>
                            </div>
                            <div class="activity-stat">
                                <div class="activity-stat-num">${{summary.unique_windows_visited || 0}}</div>
                                <div class="activity-stat-label">Unique Windows</div>
                            </div>
                        </div>
                        <details>
                            <summary style="cursor: pointer; color: #4CAF50; margin-bottom: 10px;">📜 View Window Activity (${{log.window_activity ? log.window_activity.length : 0}} entries)</summary>
                            <div class="activity-details">${{windowActivityHtml}}</div>
                        </details>
                        ${{appLaunchHtml ? `<details style="margin-top: 10px;"><summary style="cursor: pointer; color: #2196F3;">🚀 Apps Launched (${{log.app_launches.length}})</summary><div class="activity-details">${{appLaunchHtml}}</div></details>` : ''}}
                    `;
                    container.appendChild(card);
                }});
            }}

            function renderPage(date) {{
                currentDate = date;
                const sessions = securityData[date] || [];
                
                // 1. Update Header Stats
                document.getElementById('stat-total').innerText = sessions.length;
                const intruders = sessions.filter(s => s.status.includes('INTRUDER')).length;
                document.getElementById('stat-intruders').innerText = intruders;
                document.getElementById('last-updated').innerText = new Date().toLocaleTimeString();
                
                // 2. Update Navigation
                document.getElementById('date-display').innerText = date;
                
                const idx = allDates.indexOf(date);
                const prevBtn = document.getElementById('btn-prev');
                const nextBtn = document.getElementById('btn-next');
                
                if (idx > 0) {{
                    prevBtn.classList.remove('disabled');
                    prevBtn.onclick = () => renderPage(allDates[idx - 1]);
                }} else {{
                    prevBtn.classList.add('disabled');
                    prevBtn.onclick = null;
                }}
                
                if (idx < allDates.length - 1) {{
                    nextBtn.classList.remove('disabled');
                    nextBtn.onclick = () => renderPage(allDates[idx + 1]);
                }} else {{
                    nextBtn.classList.add('disabled');
                    nextBtn.onclick = null;
                }}
                
                // Update Dropdown
                const select = document.getElementById('date-select');
                select.innerHTML = '<option value="">Jump to Date...</option>';
                // Reverse order for dropdown
                [...allDates].reverse().forEach(d => {{
                    const opt = document.createElement('option');
                    opt.value = d;
                    opt.innerText = d;
                    if (d === date) opt.selected = true;
                    select.appendChild(opt);
                }});

                // 3. Render Timeline
                const timelineBar = document.getElementById('timeline-bar');
                timelineBar.innerHTML = '';
                sessions.forEach(s => {{
                    try {{
                        const parts = s.time.split(':');
                        const h = parseInt(parts[0]);
                        const m = parseInt(parts[1]);
                        const totalMin = h * 60 + m;
                        const percent = (totalMin / 1440) * 100;
                        
                        let cls = 'safe';
                        if (s.status.includes('INTRUDER')) cls = 'alert';
                        else if (s.status.includes('SPOOKY')) cls = 'spooky';
                        else if (s.status.includes('SUSPICIOUS') || s.status.includes('Scanning')) cls = 'suspicious';
                        
                        const marker = document.createElement('div');
                        marker.className = `timeline-marker ${{cls}}`;
                        marker.style.left = `${{percent}}%`;
                        marker.title = `${{s.time}} - ${{s.status}}`;
                        timelineBar.appendChild(marker);
                    }} catch(e) {{}}
                }});

                // 4. Render Sessions
                const container = document.getElementById('sessions');
                container.innerHTML = '';
                
                sessions.forEach(s => {{
                    let cssClass = "alert";
                    let statusText = "⚠️ Analyzing...";
                    
                    if (s.status.includes("INTRUDER")) {{
                        cssClass = "alert";
                        statusText = "🚨 INTRUDER DETECTED";
                    }} else if (s.status.includes("SPOOKY")) {{
                        cssClass = "spooky";
                        statusText = "👻 Spooky (No Face)";
                    }} else if (s.status.includes("SUSPICIOUS")) {{
                        cssClass = "suspicious";
                        statusText = "⚠️ Suspicious (No Face)";
                    }} else if (s.status.includes("Scanning")) {{
                        cssClass = "suspicious";
                        statusText = "⚠️ Suspicious (Scanning)";
                    }} else if (s.status.includes("FACE_DETECTED")) {{
                        cssClass = "safe";
                        statusText = "👤 Face Detected";
                    }} else if (s.status.includes("OWNER") || s.status.includes("SAFE")) {{
                        cssClass = "safe";
                        statusText = "✅ Owner Verified";
                    }}
                    
                    const card = document.createElement('div');
                    card.className = `session-card ${{cssClass}}`;
                    // Add data attribute for filtering
                    if (cssClass === 'alert') card.dataset.type = 'alert';
                    else if (cssClass === 'spooky') card.dataset.type = 'spooky';
                    else if (cssClass === 'suspicious') card.dataset.type = 'suspicious';
                    else card.dataset.type = 'safe';
                    
                    const imgListStr = s.images.join(',');
                    
                    let imgsHtml = '';
                    s.images.forEach((img, i) => {{
                        // Escape quotes just in case
                        const safeList = imgListStr.replace(/'/g, "\\'");
                        imgsHtml += `<img src="${{img}}" onclick="openLightbox(${{i}}, '${{safeList}}')">`;
                    }});
                    
                    card.innerHTML = `
                        <div class="session-header">
                            <div class="time-badge">🕒 ${{s.time}}</div>
                            <div class="status-badge">${{statusText}}</div>
                        </div>
                        <div class="gallery">
                            ${{imgsHtml}}
                        </div>
                    `;
                    container.appendChild(card);
                }});
                
                // Re-apply current filter
                applyFilter(currentFilter);
            }}

            function filterSessions(type) {{
                currentFilter = type;
                applyFilter(type);
                
                // Update buttons UI
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                event.target.classList.add('active');
            }}
            
            function applyFilter(type) {{
                const cards = document.querySelectorAll('.session-card');
                cards.forEach(c => {{
                    if (type === 'all') {{
                        c.style.display = 'block';
                    }} else {{
                        c.style.display = c.dataset.type === type ? 'block' : 'none';
                    }}
                }});
            }}
            
            function openLightbox(index, imagesStr) {{
                currentImages = imagesStr.split(',');
                currentIndex = index;
                updateLightbox();
                document.getElementById('lightbox').style.display = 'flex';
            }}
            
            function updateLightbox() {{
                const img = document.getElementById('lb-img');
                img.src = currentImages[currentIndex];
            }}
            
            function nextImage(e) {{
                if(e) e.stopPropagation();
                currentIndex = (currentIndex + 1) % currentImages.length;
                updateLightbox();
            }}
            
            function prevImage(e) {{
                if(e) e.stopPropagation();
                currentIndex = (currentIndex - 1 + currentImages.length) % currentImages.length;
                updateLightbox();
            }}

            function closeLightbox() {{
                document.getElementById('lightbox').style.display = 'none';
            }}
            
            function jumpToDate(select) {{
                const date = select.value;
                if(date) renderPage(date);
            }}
            
            // Keyboard Nav
            document.addEventListener('keydown', function(event) {{
                if (document.getElementById('lightbox').style.display === 'flex') {{
                    if (event.key === "Escape") closeLightbox();
                    if (event.key === "ArrowRight") nextImage();
                    if (event.key === "ArrowLeft") prevImage();
                }}
            }});
            
            window.onload = init;
        </script>
    </head>
    <body>
        <div class="header">
            <div>
                <h1 style="margin:0">🛡️ Security Dashboard</h1>
                <div style="color: #666; margin-top: 5px;">Daily Access Log <span style="font-size: 12px; margin-left: 10px; opacity: 0.5;">Last Updated: <span id="last-updated"></span></span></div>
            </div>
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-num" id="stat-total">0</div>
                    <div class="stat-label">Total Logins</div>
                </div>
                <div class="stat-box">
                    <div class="stat-num" style="color: #ff4444" id="stat-intruders">0</div>
                    <div class="stat-label">Intruders</div>
                </div>
                <div class="stat-box">
                    <div class="stat-num" style="color: #ff9800" id="activity-count">0</div>
                    <div class="stat-label">Activity Logs</div>
                </div>
            </div>
        </div>

        <!-- Tab Navigation -->
        <div class="tab-bar">
            <button id="tab-photos" class="tab-btn active" onclick="switchTab('photos')">📷 Photos & Sessions</button>
            <button id="tab-activity" class="tab-btn activity-tab" onclick="switchTab('activity')">📋 Activity Logs</button>
        </div>

        <!-- Photos Tab Content -->
        <div id="content-photos" class="tab-content active">
            <div class="nav-bar">
                <div id="btn-prev" class="nav-btn">← Previous Day</div>
                <span class="date-display" id="date-display">Loading...</span>
                <div id="btn-next" class="nav-btn">Next Day →</div>
                
                <div style="flex-grow: 1;"></div>
                
                <select id="date-select" class="date-select" onchange="jumpToDate(this)">
                    <option value="">Jump to Date...</option>
                </select>
            </div>

            <div class="timeline-container">
                <div style="color: #aaa; font-size: 14px; font-weight: bold; margin-bottom: 10px;">ACTIVITY TIMELINE (24H)</div>
                <div class="timeline-bar" id="timeline-bar">
                    <!-- Markers injected by JS -->
                </div>
                <div class="timeline-labels">
                    <span>00:00</span>
                    <span>06:00</span>
                    <span>12:00</span>
                    <span>18:00</span>
                    <span>23:59</span>
                </div>
            </div>

            <div class="filter-bar">
                <button class="filter-btn active" onclick="filterSessions('all')">All Events</button>
                <button class="filter-btn" onclick="filterSessions('safe')">✅ Safe</button>
                <button class="filter-btn alert-filter" onclick="filterSessions('alert')">🚨 Intruders</button>
                <button class="filter-btn" style="color: #9C27B0;" onclick="filterSessions('spooky')">👻 Spooky</button>
                <button class="filter-btn" style="color: #FFC107;" onclick="filterSessions('suspicious')">⚠️ Suspicious</button>
            </div>

            <div id="sessions">
                <!-- Sessions injected by JS -->
            </div>
        </div>
        
        <!-- Activity Logs Tab Content -->
        <div id="content-activity" class="tab-content">
            <div style="background: #1e1e1e; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 10px 0; color: #ff9800;">📋 Activity Monitor Logs</h3>
                <p style="margin: 0; color: #888; font-size: 13px;">These logs are recorded when authentication fails (INTRUDER or SUSPICIOUS detected). They track all app usage and window activity for 30 minutes after the alert.</p>
            </div>
            <div id="activity-logs">
                <!-- Activity logs injected by JS -->
            </div>
        </div>
        
        <div id="lightbox" class="lightbox" onclick="closeLightbox()">
            <div class="close-hint">&times;</div>
            <div class="lb-nav lb-prev" onclick="prevImage(event)">&#10094;</div>
            <div class="lb-nav lb-next" onclick="nextImage(event)">&#10095;</div>
            <img id="lb-img" src="" onclick="event.stopPropagation()">
        </div>
    </body>
    </html>
    """
    
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"Error writing HTML: {e}")

def capture_photo():
    # Setup logging with rotation
    def log(message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        # Read existing log and rotate if needed
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                # Keep only the last MAX_LOG_LINES - 1 lines
                if len(lines) >= MAX_LOG_LINES:
                    lines = lines[-(MAX_LOG_LINES - 1):]
                    with open(LOG_FILE, "w", encoding="utf-8") as f:
                        f.writelines(lines)
        except (IOError, OSError):
            pass
        
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)

    log("Script started")
    
    # CRITICAL: Wait for workstation to be UNLOCKED (password entered)
    # This prevents photos during boot/lock screen before password entry
    if is_workstation_locked():
        log("Workstation is locked - waiting for user to enter password...")
        if not wait_for_unlock(timeout=120, log_func=log):
            log("ABORT: Workstation still locked after 2 minutes - exiting")
            return  # Exit without taking photos
    
    # Additional check: Wait for desktop session to be fully ready
    log("Checking desktop session...")
    if not wait_for_session_ready(timeout=30, log_func=log):
        log("WARNING: Session may not be fully ready, continuing anyway...")
    
    # Small delay to ensure everything is stabilized after unlock
    time.sleep(STARTUP_DELAY)
    log(f"Desktop ready, starting capture after {STARTUP_DELAY}s stabilization delay")

    # Ensure the directory exists for saving photos
    base_dir = PHOTOS_DIR
    
    # Cleanup old photos (older than configured retention period)
    # Run cleanup BEFORE creating today's folder to avoid deleting it
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=PHOTO_RETENTION_DAYS)
        if os.path.exists(base_dir):
            for root, dirs, files in os.walk(base_dir, topdown=False):
                for name in files:
                    path = os.path.join(root, name)
                    try:
                        if datetime.datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                            os.remove(path)
                    except (OSError, IOError, ValueError):
                        pass
                for name in dirs:
                    path = os.path.join(root, name)
                    try:
                        if not os.listdir(path): # Remove empty folders
                            os.rmdir(path)
                    except (OSError, IOError):
                        pass
    except Exception as e:
        log(f"Cleanup error: {e}")

    # Create a specific folder for THIS login session
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    session_time = datetime.datetime.now().strftime("%H-%M-%S")
    session_dir = os.path.join(base_dir, f"{today_str}_{session_time}_Scanning")
    os.makedirs(session_dir)

    # Load Modern AI Models (YuNet + SFace)
    # 1. YuNet (Detection)
    detector = cv2.FaceDetectorYN.create(
        FACE_DETECTION_MODEL,
        "",
        (320, 320), # Initial size, will update per frame
        DETECTION_CONFIDENCE,  # Score threshold
        0.3,  # NMS threshold
        5000
    )

    # 2. SFace (Recognition)
    recognizer = cv2.FaceRecognizerSF.create(
        FACE_RECOGNITION_MODEL,
        ""
    )
    
    # Load Owner Embedding (SFace version)
    owner_embed = None
    if os.path.exists(OWNER_EMBEDDING_FILE):
        try:
            owner_embed = np.load(OWNER_EMBEDDING_FILE)
            log("Owner embedding (SFace) loaded.")
        except (IOError, ValueError) as e:
            log(f"Failed to load owner embedding: {e}")

    # Status flags
    faces_found = False
    owner_detected = False
    
    # Gather System Info ONCE (to avoid delay between shots)
    sys_info = get_system_info()
    
    # Get power status and adaptive settings
    power_status = get_power_status()
    adaptive = get_adaptive_settings(power_status)
    log(f"Power: {power_status['power_mode']} ({power_status['percent']}%) - Using {adaptive['resolution']} resolution")
    
    # Check if we should skip due to low battery
    if power_status['should_skip']:
        log("SKIPPING: Battery too low for capture")
        return

    # Helper function to open camera with adaptive resolution
    def open_camera():
        log("Opening camera...")
        cap = cv2.VideoCapture(0)
        # Use adaptive resolution based on power status
        res = adaptive['resolution']
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, res[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, res[1])
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        return cap

    def recognize_face_multi_sample(frame, face, recognizer, owner_embed):
        """
        Advanced recognition with multi-sample verification.
        Takes multiple feature extractions and votes on the result.
        Returns: (is_owner: bool, confidence: float, label: str)
        """
        if owner_embed is None:
            return False, 0.0, "Unknown"
        
        # Single sample mode (faster, uses less battery)
        if not MULTI_SAMPLE_VERIFICATION:
            face_align = recognizer.alignCrop(frame, face)
            face_feature = recognizer.feature(face_align)
            score = recognizer.match(owner_embed, face_feature, cv2.FaceRecognizerSF_FR_COSINE)
            
            if score > RECOGNITION_THRESHOLD:
                return True, score, f"OWNER ({score:.2f})"
            else:
                return False, score, f"INTRUDER ({score:.2f})"
        
        # Multi-sample verification (more accurate)
        scores = []
        for _ in range(VERIFICATION_SAMPLES):
            try:
                face_align = recognizer.alignCrop(frame, face)
                face_feature = recognizer.feature(face_align)
                score = recognizer.match(owner_embed, face_feature, cv2.FaceRecognizerSF_FR_COSINE)
                scores.append(score)
            except Exception:
                continue
        
        if not scores:
            return False, 0.0, "Unknown"
        
        # Calculate average and count votes
        avg_score = sum(scores) / len(scores)
        owner_votes = sum(1 for s in scores if s > RECOGNITION_THRESHOLD)
        
        # Need minimum votes to confirm as owner
        if owner_votes >= MIN_CONFIDENCE_VOTES:
            return True, avg_score, f"OWNER ({avg_score:.2f})"
        else:
            return False, avg_score, f"INTRUDER ({avg_score:.2f})"

    def process_and_save(frame, faces):
        nonlocal owner_detected, faces_found
        
        if faces is not None:
            faces_found = True
            
            for face in faces:
                # Check face quality score (last element in face array)
                face_score = face[-1] if len(face) > 4 else 1.0
                
                # Get Box
                box = face[0:4].astype(int)
                
                startX, startY, w_box, h_box = box
                endX = startX + w_box
                endY = startY + h_box
                
                # Skip low quality faces for recognition
                if face_score < FACE_QUALITY_THRESHOLD:
                    name = f"Low Quality ({face_score:.2f})"
                    color = (128, 128, 128)  # Gray
                else:
                    # Use advanced multi-sample recognition
                    is_owner, confidence, name = recognize_face_multi_sample(
                        frame, face, recognizer, owner_embed
                    )
                    
                    if is_owner:
                        color = (0, 255, 0)  # Green
                        owner_detected = True
                    else:
                        color = (0, 0, 255)  # Red

                # Draw Box & Label
                y = startY - 10 if startY - 10 > 10 else startY + 10
                cv2.rectangle(frame, (startX, startY), (endX, endY), color, 2)
                cv2.putText(frame, name, (startX, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # Prepare timestamps
        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
        filename_ts = now.strftime("%H-%M-%S_%f") 
        
        # Add power status to overlay
        pwr = power_status
        power_text = f"{'🔋' if pwr['on_battery'] else '🔌'} {pwr['percent']}%"

        # Add timestamp text to the image (Yellow color)
        cv2.putText(frame, timestamp_str, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2, cv2.LINE_AA)
        
        # Add power status (top right)
        text_size = cv2.getTextSize(power_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        cv2.putText(frame, power_text, (frame.shape[1] - text_size[0] - 20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)

        # Add System Info Overlay (Bottom Left, White text with Black outline)
        y_pos = frame.shape[0] - 30 # Start from bottom
        for info_line in reversed(sys_info): # Draw bottom-up
            # Draw black outline for readability
            cv2.putText(frame, info_line, (20, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
            # Draw white text
            cv2.putText(frame, info_line, (20, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            y_pos -= 30 # Move up for next line

        filename = os.path.join(session_dir, f"{filename_ts}.jpg")
        cv2.imwrite(filename, frame)
        log(f"Photo saved: {filename}")

    # Smart Capture Loop (Trap Mode) with Battery Awareness
    # Strategy:
    # 1. Open Camera -> Burst photos (count based on power status)
    # 2. Analyze photos with multi-sample verification
    # 3. If Face Found -> Exit
    # 4. If No Face:
    #    - 1st attempt: Mark as SPOOKY
    #    - 2nd attempt: Send Telegram alert immediately
    
    burst_count = adaptive['burst_count']
    retry_delay = adaptive['retry_delay']
    attempt_number = 0  # Track how many no-face attempts
    
    start_time = time.time()
    
    while (time.time() - start_time) < MAX_CAPTURE_DURATION:
        # Refresh power status each iteration (battery may have changed)
        power_status = get_power_status()
        if power_status['should_skip']:
            log("Battery critically low, stopping capture")
            break
            
        # Open camera for this attempt
        cap = open_camera()
        
        if not cap.isOpened():
            log("Failed to open camera")
            break

        # BURST MODE: Take photos based on power mode
        attempt_number += 1
        log(f"Attempt {attempt_number}: Taking {burst_count} burst photos ({power_status['power_mode']} mode)...")
        
        current_burst_faces_found = False
        
        for i in range(burst_count):
            # Robust Frame Capture with Brightness Check
            ret = False
            frame = None
            
            # Try to get a VALID (non-black) frame
            # We poll for up to 5 seconds.
            for attempt in range(100):
                ret, frame = cap.read()
                if ret:
                    # Check brightness (0-255)
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    avg_brightness = np.mean(gray)
                    
                    # If brightness is too low, skip and wait for auto-exposure
                    if avg_brightness > 30:
                        break
                
                time.sleep(0.05)
            
            if not ret or frame is None:
                log(f"Failed to capture valid frame {i+1} (Timed out or too dark)")
                continue
            
            # OPTIMIZATION: Resize frame for faster detection
            # Detection runs at small resolution, recognition uses full frame
            h, w, _ = frame.shape
            det_w, det_h = DETECTION_RESOLUTION
            
            # Create smaller frame for detection (faster)
            if w > det_w or h > det_h:
                scale = min(det_w / w, det_h / h)
                small_frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                small_h, small_w = small_frame.shape[:2]
            else:
                small_frame = frame
                small_h, small_w = h, w
                scale = 1.0
            
            # Update detector input size to small frame
            detector.setInputSize((small_w, small_h))

            # Detect Faces on SMALL frame (YuNet) - FAST
            _, faces_small = detector.detect(small_frame)
            
            # Scale face coordinates back to original frame size
            faces = None
            if faces_small is not None and scale != 1.0:
                faces = faces_small.copy()
                # Scale all coordinate values (x, y, w, h, landmarks)
                faces[:, :14] = faces[:, :14] / scale
            elif faces_small is not None:
                faces = faces_small
            
            if faces is not None:
                current_burst_faces_found = True
            
            # Save and Process (uses FULL frame for quality)
            process_and_save(frame, faces)
            
            # Very small delay between shots (0.2s) to be faster
            time.sleep(0.2)
            
        cap.release()
        
        # Update Dashboard immediately so user can see photos
        try:
            generate_daily_report(base_dir)
        except Exception as e:
            log(f"HTML Error: {e}")

        # Decision Logic
        if current_burst_faces_found:
            log("Face detected in burst. Stopping loop.")
            break
        else:
            # No face detected in this burst
            if attempt_number == 1:
                # First attempt - mark as SPOOKY
                log("👻 SPOOKY: No face on first attempt. Retrying...")
                # Rename folder to SPOOKY temporarily
                spooky_dir = os.path.join(base_dir, f"{today_str}_{session_time}_SPOOKY")
                try:
                    os.rename(session_dir, spooky_dir)
                    session_dir = spooky_dir
                except OSError:
                    pass
            elif attempt_number == 2:
                # Second attempt - send immediate Telegram alert
                log("🚨 ALERT: No face on second attempt! Sending Telegram...")
                send_telegram_alert("SPOOKY_NO_FACE", session_dir)
            
            log(f"No face detected (attempt {attempt_number}). Waiting {retry_delay} seconds...")
            time.sleep(retry_delay)

    # Cleanup logic (outside loop)
    # Rename the folder based on face detection
    # Logic:
    # 1. Owner Detected -> SAFE_OWNER
    # 2. Face Detected (But not owner) -> INTRUDER_DETECTED
    # 3. No Face -> SUSPICIOUS
    
    final_status = "SUSPICIOUS"
    if owner_detected:
        final_status = "SAFE_OWNER"
    elif faces_found:
        final_status = "INTRUDER_DETECTED"
        
    new_session_dir = os.path.join(base_dir, f"{today_str}_{session_time}_{final_status}")
    try:
        os.rename(session_dir, new_session_dir)
        session_dir = new_session_dir
    except OSError as e:
        log(f"Failed to rename session folder: {e}")

    # TELEGRAM ALERT: Send for Intruder or Suspicious
    if "INTRUDER" in final_status or "SUSPICIOUS" in final_status:
        log("Sending Telegram alert...")
        send_telegram_alert(final_status, session_dir)
        
        # START ACTIVITY MONITOR: Track all app usage after authentication failure
        if ACTIVITY_MONITOR_AVAILABLE:
            log("🔍 Starting Activity Monitor (authentication failed)...")
            try:
                # Monitor for 30 minutes (1800 seconds) in background
                monitor_pid = start_activity_monitor(trigger_reason=final_status, duration=1800)
                if monitor_pid:
                    log(f"Activity Monitor started (PID: {monitor_pid}) - Tracking all app activity for 30 minutes")
                else:
                    log("Failed to start Activity Monitor")
            except Exception as e:
                log(f"Activity Monitor Error: {e}")
        else:
            log("Activity Monitor not available - skipping activity logging")

    # Generate/Update HTML Gallery
    try:
        generate_daily_report(base_dir)
    except Exception as e:
        log(f"HTML Error: {e}")

    try:
        cv2.destroyAllWindows()
    except cv2.error:
        pass
    log("Script finished")

if __name__ == "__main__":
    capture_photo()
