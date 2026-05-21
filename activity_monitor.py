"""
Activity Monitor - Logs all application activity when authentication fails
Runs silently in the background to track app usage, window changes, and user activity
"""

import os
import sys
import time
import datetime
import json
import ctypes
import subprocess
import threading
import psutil
from collections import defaultdict

# Import configuration
try:
    from config import (
        BASE_DIR,
        ACTIVITY_MONITOR_ENABLED,
        ACTIVITY_MONITOR_DURATION,
        ACTIVITY_LOG_INTERVAL,
        ACTIVITY_NOTIFY_DELAY,
        ACTIVITY_NOTIFY_TITLE,
        ACTIVITY_NOTIFY_MESSAGE
    )
    MONITOR_DURATION = ACTIVITY_MONITOR_DURATION
    LOG_INTERVAL = ACTIVITY_LOG_INTERVAL
    NOTIFICATION_DELAY = ACTIVITY_NOTIFY_DELAY
    NOTIFY_TITLE = ACTIVITY_NOTIFY_TITLE
    NOTIFY_MESSAGE = ACTIVITY_NOTIFY_MESSAGE
except ImportError:
    BASE_DIR = r"C:\security\script"
    MONITOR_DURATION = 1800  # 30 minutes default monitoring duration
    LOG_INTERVAL = 2  # Check every 2 seconds
    NOTIFICATION_DELAY = 180  # 3 minutes
    NOTIFY_TITLE = "Minecraft"
    NOTIFY_MESSAGE = "Background sync active. Run stop_monitor.bat to cancel."

# Configuration
ACTIVITY_LOG_DIR = os.path.join(BASE_DIR, "activity_logs")
STOP_SIGNAL_FILE = os.path.join(BASE_DIR, ".stop_monitor")

# Ensure log directory exists
os.makedirs(ACTIVITY_LOG_DIR, exist_ok=True)

def show_game_notification(title="Minecraft", message="World saved"):
    """Show a simple Windows balloon notification"""
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        # Simple balloon tip
        script = f'''
        Add-Type -AssemblyName System.Windows.Forms
        $n = New-Object System.Windows.Forms.NotifyIcon
        $n.Icon = [System.Drawing.SystemIcons]::Application
        $n.BalloonTipTitle = "{title}"
        $n.BalloonTipText = "{message}"
        $n.Visible = $true
        $n.ShowBalloonTip(3000)
        Start-Sleep -Seconds 4
        $n.Dispose()
        '''
        
        subprocess.Popen(
            ['powershell', '-Command', script],
            startupinfo=startupinfo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except:
        pass

def get_active_window_title():
    """Get the title of the currently active window"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value if buf.value else "Unknown"
    except Exception:
        return "Unknown"

def get_active_window_process():
    """Get the process name of the currently active window"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            if proc.info['pid'] == pid.value:
                return {
                    'name': proc.info['name'],
                    'exe': proc.info['exe'] or 'Unknown',
                    'pid': pid.value
                }
    except Exception:
        pass
    return {'name': 'Unknown', 'exe': 'Unknown', 'pid': 0}

def get_running_apps():
    """Get list of all currently running applications with windows"""
    apps = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'create_time', 'cpu_percent', 'memory_percent']):
            try:
                pinfo = proc.info
                # Filter to only show user applications (not system processes)
                if pinfo['exe'] and 'Windows' not in pinfo['exe']:
                    apps.append({
                        'name': pinfo['name'],
                        'exe': pinfo['exe'],
                        'pid': pinfo['pid'],
                        'started': datetime.datetime.fromtimestamp(pinfo['create_time']).strftime('%Y-%m-%d %H:%M:%S'),
                        'cpu': round(pinfo['cpu_percent'], 2),
                        'memory': round(pinfo['memory_percent'], 2)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return apps

def get_browser_history():
    """Attempt to get recent browser activity (Chrome/Edge)"""
    history = []
    try:
        # Chrome history location
        chrome_history = os.path.expanduser(r'~\AppData\Local\Google\Chrome\User Data\Default\History')
        if os.path.exists(chrome_history):
            history.append({'browser': 'Chrome', 'history_path': chrome_history})
        
        # Edge history location
        edge_history = os.path.expanduser(r'~\AppData\Local\Microsoft\Edge\User Data\Default\History')
        if os.path.exists(edge_history):
            history.append({'browser': 'Edge', 'history_path': edge_history})
    except Exception:
        pass
    return history

def get_recent_files():
    """Get recently accessed files from Windows Recent folder"""
    recent = []
    try:
        recent_folder = os.path.expanduser(r'~\AppData\Roaming\Microsoft\Windows\Recent')
        if os.path.exists(recent_folder):
            files = os.listdir(recent_folder)
            # Sort by modification time, get most recent
            files_with_time = []
            for f in files:
                filepath = os.path.join(recent_folder, f)
                try:
                    mtime = os.path.getmtime(filepath)
                    files_with_time.append((f, mtime))
                except:
                    pass
            
            files_with_time.sort(key=lambda x: x[1], reverse=True)
            for f, mtime in files_with_time[:20]:  # Last 20 recent files
                recent.append({
                    'file': f.replace('.lnk', ''),
                    'accessed': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
    except Exception:
        pass
    return recent

def get_usb_devices():
    """Get connected USB devices"""
    devices = []
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            ['wmic', 'path', 'Win32_USBHub', 'get', 'DeviceID,Name', '/format:csv'],
            capture_output=True, text=True, startupinfo=startupinfo
        )
        lines = result.stdout.strip().split('\n')
        for line in lines[2:]:  # Skip header
            if line.strip():
                parts = line.split(',')
                if len(parts) >= 3:
                    devices.append({
                        'device_id': parts[1],
                        'name': parts[2] if len(parts) > 2 else 'Unknown'
                    })
    except Exception:
        pass
    return devices

def get_network_connections():
    """Get active network connections"""
    connections = []
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'ESTABLISHED':
                try:
                    proc = psutil.Process(conn.pid) if conn.pid else None
                    laddr = conn.laddr
                    raddr = conn.raddr
                    local_str = f"{laddr[0]}:{laddr[1]}" if laddr else "N/A"
                    remote_str = f"{raddr[0]}:{raddr[1]}" if raddr else "N/A"
                    connections.append({
                        'local': local_str,
                        'remote': remote_str,
                        'process': proc.name() if proc else "Unknown",
                        'pid': conn.pid
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, IndexError):
                    pass
    except Exception:
        pass
    return connections

class ActivityMonitor:
    def __init__(self, session_id, trigger_reason="UNKNOWN", silent=False):
        self.session_id = session_id
        self.trigger_reason = trigger_reason
        self.silent = silent  # When True, suppress all print statements (for background mode)
        self.start_time = datetime.datetime.now()
        self.log_file = os.path.join(
            ACTIVITY_LOG_DIR, 
            f"activity_{self.start_time.strftime('%Y-%m-%d_%H-%M-%S')}_{trigger_reason}.json"
        )
        self.running = False
        self.activity_log = {
            'session_id': session_id,
            'trigger_reason': trigger_reason,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': None,
            'system_info': self._get_system_info(),
            'initial_state': {
                'running_apps': get_running_apps(),
                'recent_files': get_recent_files(),
                'usb_devices': get_usb_devices(),
                'network_connections': get_network_connections()
            },
            'window_activity': [],
            'app_launches': [],
            'app_closures': [],
            'file_access': [],
            'summary': {}
        }
        self.tracked_apps = set()
        self.window_history = []
        self.app_usage_time = defaultdict(float)
        self.last_window = None
        self.last_window_time = time.time()
    
    def _log(self, message):
        """Print message only if not in silent mode (handles Unicode for background processes)"""
        if not self.silent:
            try:
                print(message)
            except (UnicodeEncodeError, OSError):
                # Handle encoding errors in background mode or no console
                try:
                    # Try printing ASCII-safe version
                    safe_message = message.encode('ascii', 'replace').decode('ascii')
                    print(safe_message)
                except:
                    pass  # Suppress all output if printing fails
        
    def _get_system_info(self):
        """Get system information"""
        info = {}
        try:
            info['hostname'] = os.environ.get('COMPUTERNAME', 'Unknown')
            info['username'] = os.environ.get('USERNAME', 'Unknown')
            ver = sys.getwindowsversion()
            info['os'] = f"Windows {ver.major}.{ver.minor}"
            
            battery = psutil.sensors_battery()
            if battery:
                info['battery'] = f"{battery.percent}% ({'Charging' if battery.power_plugged else 'Battery'})"
            else:
                info['battery'] = 'Desktop (No Battery)'
        except Exception:
            pass
        return info
    
    def _update_app_usage(self, current_window, current_process):
        """Track time spent in each application"""
        current_time = time.time()
        
        if self.last_window and self.last_window != current_window:
            # Window changed, update time for previous window
            time_spent = current_time - self.last_window_time
            self.app_usage_time[self.last_window] += time_spent
        
        self.last_window = current_window
        self.last_window_time = current_time
    
    def _check_new_apps(self):
        """Check for newly launched or closed applications"""
        current_apps = set()
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['exe']:
                    current_apps.add((proc.info['pid'], proc.info['name'], proc.info['exe']))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Check for new apps
        for app in current_apps - self.tracked_apps:
            pid, name, exe = app
            self.activity_log['app_launches'].append({
                'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'name': name,
                'exe': exe,
                'pid': pid
            })
        
        # Check for closed apps
        for app in self.tracked_apps - current_apps:
            pid, name, exe = app
            self.activity_log['app_closures'].append({
                'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'name': name,
                'exe': exe,
                'pid': pid
            })
        
        self.tracked_apps = current_apps
    
    def _log_activity(self):
        """Log current window activity"""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        window_title = get_active_window_title()
        process_info = get_active_window_process()
        
        # Track window changes
        if not self.window_history or self.window_history[-1]['window'] != window_title:
            entry = {
                'time': timestamp,
                'window': window_title,
                'process': process_info['name'],
                'exe': process_info['exe']
            }
            self.activity_log['window_activity'].append(entry)
            self.window_history.append(entry)
            
            # Update app usage tracking
            self._update_app_usage(window_title, process_info['name'])
        
        # Check for new/closed apps
        self._check_new_apps()
    
    def _save_log(self):
        """Save activity log to file"""
        try:
            # Update end time and summary
            self.activity_log['end_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Generate summary
            duration = (datetime.datetime.now() - self.start_time).total_seconds()
            self.activity_log['summary'] = {
                'total_duration_seconds': round(duration),
                'total_duration_minutes': round(duration / 60, 2),
                'unique_windows_visited': len(set(w['window'] for w in self.activity_log['window_activity'])),
                'apps_launched': len(self.activity_log['app_launches']),
                'apps_closed': len(self.activity_log['app_closures']),
                'window_switches': len(self.activity_log['window_activity']),
                'top_apps_by_time': dict(sorted(self.app_usage_time.items(), key=lambda x: x[1], reverse=True)[:10])
            }
            
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.activity_log, f, indent=2, ensure_ascii=False)
                
            self._log(f"Activity log saved: {self.log_file}")
        except Exception as e:
            self._log(f"Failed to save log: {e}")
    
    def start(self, duration=MONITOR_DURATION):
        """Start monitoring activity"""
        self.running = True
        self.last_notification_time = 0
        self._log(f"[Activity Monitor] Started - Reason: {self.trigger_reason}")
        self._log(f"   Monitoring for {duration} seconds ({duration/60:.1f} minutes)")
        self._log(f"   Log file: {self.log_file}")
        
        # Initialize tracked apps
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['exe']:
                    self.tracked_apps.add((proc.info['pid'], proc.info['name'], proc.info['exe']))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        start_time = time.time()
        
        try:
            save_counter = 0
            while self.running and (time.time() - start_time) < duration:
                # Check for stop signal file
                if os.path.exists(STOP_SIGNAL_FILE):
                    self._log("Stop signal received - saving log and shutting down...")
                    try:
                        os.remove(STOP_SIGNAL_FILE)
                    except OSError:
                        pass
                    break
                
                self._log_activity()
                
                # Auto-save every 30 iterations (~60 seconds) to prevent data loss
                save_counter += 1
                if save_counter >= 30:
                    self._save_log()
                    save_counter = 0
                
                # Send notification every 3 minutes
                elapsed = time.time() - start_time
                if elapsed - self.last_notification_time >= NOTIFICATION_DELAY:
                    show_game_notification(NOTIFY_TITLE, NOTIFY_MESSAGE)
                    self.last_notification_time = elapsed
                
                time.sleep(LOG_INTERVAL)
        except KeyboardInterrupt:
            self._log("\nMonitoring interrupted by user")
        finally:
            self.stop()
    
    def stop(self):
        """Stop monitoring and save log"""
        self.running = False
        self._save_log()
        self._log(f"[Activity Monitor] Stopped")
        self._log(f"   Total window switches: {len(self.activity_log['window_activity'])}")
        self._log(f"   Apps launched during session: {len(self.activity_log['app_launches'])}")

def start_activity_monitor(trigger_reason="UNKNOWN", duration=MONITOR_DURATION):
    """Start the activity monitor in a background thread"""
    session_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    monitor = ActivityMonitor(session_id, trigger_reason)
    
    # Run in background thread
    thread = threading.Thread(target=monitor.start, args=(duration,), daemon=True)
    thread.start()
    
    return monitor, thread

def run_detached(trigger_reason="UNKNOWN", duration=MONITOR_DURATION):
    """Run the activity monitor as a separate detached process (hidden)"""
    try:
        script_path = os.path.abspath(__file__)
        
        # Use pythonw.exe for hidden window, or python.exe if not available
        python_exe = sys.executable
        pythonw_exe = python_exe.replace('python.exe', 'pythonw.exe')
        
        if os.path.exists(pythonw_exe):
            exe = pythonw_exe
        else:
            exe = python_exe
        
        # Start detached process
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        
        process = subprocess.Popen(
            [exe, script_path, '--background', trigger_reason, str(duration)],
            startupinfo=startupinfo,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        print(f"Activity monitor started in background (PID: {process.pid})")
        return process.pid
        
    except Exception as e:
        print(f"Failed to start detached monitor: {e}")
        return None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Activity Monitor for Security System")
    parser.add_argument('--background', action='store_true', help='Run in background mode')
    parser.add_argument('trigger', nargs='?', default='MANUAL_TEST', help='Trigger reason')
    parser.add_argument('duration', nargs='?', type=int, default=MONITOR_DURATION, help='Monitoring duration in seconds')
    
    args = parser.parse_args()
    
    if args.background or '--background' in sys.argv:
        # Running in background mode (silent - no console output)
        trigger = args.trigger if args.trigger != '--background' else 'UNKNOWN'
        if trigger == '--background':
            trigger = sys.argv[2] if len(sys.argv) > 2 else 'UNKNOWN'
        duration = args.duration
        if len(sys.argv) > 3:
            try:
                duration = int(sys.argv[3])
            except:
                pass
        
        session_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        monitor = ActivityMonitor(session_id, trigger, silent=True)  # Silent mode for background
        monitor.start(duration)
    else:
        # Interactive mode
        print("=" * 60)
        print("ACTIVITY MONITOR - Security System")
        print("=" * 60)
        print(f"Trigger Reason: {args.trigger}")
        print(f"Duration: {args.duration} seconds ({args.duration/60:.1f} minutes)")
        print("-" * 60)
        
        session_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        monitor = ActivityMonitor(session_id, args.trigger)
        monitor.start(args.duration)
