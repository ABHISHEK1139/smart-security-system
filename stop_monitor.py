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

# Use the same BASE_DIR as activity_monitor.py so the stop-signal file and the
# activity_logs/ folder always resolve to the same directory, wherever the repo lives.
try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ACTIVITY_LOG_DIR = os.path.join(BASE_DIR, "activity_logs")

STOP_SIGNAL_FILE = os.path.join(BASE_DIR, ".stop_monitor")

# Absolute path of the monitor script we are allowed to stop
MONITOR_SCRIPT = os.path.normcase(os.path.realpath(os.path.join(BASE_DIR, "activity_monitor.py")))

def _is_monitor_process(proc):
    """True only if this process is actually running this repo's activity_monitor.py.

    Compares the resolved script path from the command line instead of doing
    substring matching, so an editor/grep/other copy with the name in its
    command line is never terminated by mistake.
    """
    try:
        cmdline = proc.info.get('cmdline') or []
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    if len(cmdline) < 2:
        return False
    try:
        script_arg = os.path.normcase(os.path.realpath(os.path.abspath(cmdline[1])))
    except (OSError, ValueError):
        return False
    return script_arg == MONITOR_SCRIPT

def _find_monitor_processes():
    """Yield psutil processes that are running this repo's activity_monitor.py"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if _is_monitor_process(proc):
                yield proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def stop_activity_monitor():
    """Find and stop any running activity monitor processes (graceful then force)"""
    print("[*] Searching for running Activity Monitor processes...")

    monitor_procs = list(_find_monitor_processes())
    for proc in monitor_procs:
        print(f"   Found: PID {proc.pid}")

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
    exited = set()  # PIDs already counted as stopped (each PID counted once)
    for i in range(10):  # 10 x 0.5s = 5 seconds
        time.sleep(0.5)
        still_running = []
        for proc in monitor_procs:
            try:
                if proc.is_running():
                    still_running.append(proc)
                else:
                    exited.add(proc.pid)
            except psutil.NoSuchProcess:
                exited.add(proc.pid)
        if not still_running:
            break
        monitor_procs = still_running

    # Step 3: Force terminate any remaining
    for proc in monitor_procs:
        try:
            if proc.is_running():
                print(f"   Force terminating PID {proc.pid}...")
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Give force-terminated processes a moment, then count each PID exactly once
    try:
        gone, _ = psutil.wait_procs(monitor_procs, timeout=3)
        for proc in gone:
            exited.add(proc.pid)
    except Exception:
        pass

    stopped = len(exited)

    # Clean up signal file if still present
    try:
        if os.path.exists(STOP_SIGNAL_FILE):
            os.remove(STOP_SIGNAL_FILE)
    except OSError:
        pass

    print(f"[OK] Stopped {stopped} activity monitor process(es)")
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
    for proc in _find_monitor_processes():
        running += 1
        print(f"   Running: PID {proc.pid}")
    
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
