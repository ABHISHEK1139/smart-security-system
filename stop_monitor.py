"""
Stop Activity Monitor - Run this to stop the activity monitor if it was triggered by mistake
Also can be used to dismiss false positive alerts
"""

import os
import sys
import time
import psutil
import datetime
import json

BASE_DIR = r"C:\security\script"
ACTIVITY_LOG_DIR = os.path.join(BASE_DIR, "activity_logs")

STOP_SIGNAL_FILE = os.path.join(BASE_DIR, ".stop_monitor")

def stop_activity_monitor():
    """Find and stop any running activity monitor processes (graceful then force)"""
    stopped = 0
    
    print("[*] Searching for running Activity Monitor processes...")
    
    monitor_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and 'activity_monitor.py' in ' '.join(cmdline):
                monitor_procs.append(proc)
                print(f"   Found: PID {proc.pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if not monitor_procs:
        print("[i] No activity monitor processes found running")
        return 0
    
    # Step 1: Send graceful stop signal (creates signal file)
    print("[*] Sending graceful stop signal...")
    try:
        with open(STOP_SIGNAL_FILE, 'w') as f:
            f.write("stop")
    except OSError:
        pass
    
    # Step 2: Wait up to 5 seconds for graceful shutdown
    print("[*] Waiting for activity monitor to save log and exit...")
    for i in range(10):  # 10 x 0.5s = 5 seconds
        time.sleep(0.5)
        still_running = []
        for proc in monitor_procs:
            try:
                if proc.is_running():
                    still_running.append(proc)
            except psutil.NoSuchProcess:
                stopped += 1
        if not still_running:
            break
        monitor_procs = still_running
    
    # Step 3: Force kill any remaining
    for proc in monitor_procs:
        try:
            if proc.is_running():
                print(f"   Force terminating PID {proc.pid}...")
                proc.terminate()
                stopped += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Clean up signal file if still present
    try:
        if os.path.exists(STOP_SIGNAL_FILE):
            os.remove(STOP_SIGNAL_FILE)
    except OSError:
        pass
    
    print(f"[OK] Stopped {stopped + len([p for p in monitor_procs if not p.is_running()])} activity monitor process(es)")
    return stopped

def mark_false_positive():
    """Mark the most recent activity log as a false positive"""
    if not os.path.exists(ACTIVITY_LOG_DIR):
        print("No activity logs found")
        return
    
    # Find most recent log file
    log_files = [f for f in os.listdir(ACTIVITY_LOG_DIR) if f.endswith('.json')]
    if not log_files:
        print("No activity logs found")
        return
    
    log_files.sort(reverse=True)
    latest_log = os.path.join(ACTIVITY_LOG_DIR, log_files[0])
    
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Mark as false positive
        data['false_positive'] = True
        data['dismissed_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data['dismissed_reason'] = 'Owner dismissed - false positive'
        
        with open(latest_log, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Marked as false positive: {log_files[0]}")
        
        # Rename log file to indicate false positive
        new_name = log_files[0].replace('.json', '_FALSE_POSITIVE.json')
        new_path = os.path.join(ACTIVITY_LOG_DIR, new_name)
        os.rename(latest_log, new_path)
        print(f"   Renamed to: {new_name}")
        
    except Exception as e:
        print(f"❌ Error marking false positive: {e}")

def show_status():
    """Show current activity monitor status"""
    running = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and 'activity_monitor.py' in ' '.join(cmdline):
                running += 1
                print(f"   Running: PID {proc.pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if running == 0:
        print("ℹ️  No activity monitor currently running")
    else:
        print(f"⚠️  {running} activity monitor(s) running")
    
    # Show recent logs
    if os.path.exists(ACTIVITY_LOG_DIR):
        log_files = sorted([f for f in os.listdir(ACTIVITY_LOG_DIR) if f.endswith('.json')], reverse=True)[:5]
        if log_files:
            print("\n📁 Recent activity logs:")
            for f in log_files:
                print(f"   - {f}")

if __name__ == "__main__":
    print("=" * 60)
    print("ACTIVITY MONITOR CONTROL")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == 'stop':
            stop_activity_monitor()
        elif cmd == 'false':
            stop_activity_monitor()
            mark_false_positive()
        elif cmd == 'status':
            show_status()
        else:
            print("Usage: python stop_monitor.py [stop|false|status]")
    else:
        # Default: stop and mark as false positive
        print("\n🛑 Stopping activity monitor and marking as false positive...\n")
        stop_activity_monitor()
        mark_false_positive()
        print("\n" + "=" * 60)
        print("Done! The system incorrectly flagged you.")
        print("Consider re-registering your face with better lighting.")
        print("=" * 60)
