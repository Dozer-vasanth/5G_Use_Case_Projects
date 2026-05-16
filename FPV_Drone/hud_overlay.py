from pymavlink import mavutil
import time
import threading
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HUD_FILE = os.path.join(BASE_DIR, "hud_data.txt")

master = mavutil.mavlink_connection('udp:127.0.0.1:14551')

# Shared state
battery = "N/A"
mode = "UNKNOWN"
armed = "DISARMED"

print("Listening for Drone Telemetry...")
print(f"Writing HUD data to: {HUD_FILE}")

def mavlink_reader():
    global battery, mode, armed
    while True:
        msg = master.recv_match(blocking=True, timeout=1.0)
        if not msg:
            continue

        msg_type = msg.get_type()

        if msg_type == 'SYS_STATUS':
            battery = f"{msg.battery_remaining}"

        elif msg_type == 'HEARTBEAT':
            mode = master.flightmode
            is_armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            armed = "ARMED" if is_armed else "DISARMED"

def hud_writer():
    while True:
        hud_text = f"BATTERY {battery} MODE {mode} STATUS {armed}"
        try:
            with open(HUD_FILE, "w") as f:
                f.write(hud_text)
        except OSError as e:
            print(f"Warning: Could not write HUD file: {e}")
        time.sleep(0.5)  # Write to file only 2x per second

# Run both in parallel
t1 = threading.Thread(target=mavlink_reader, daemon=True)
t2 = threading.Thread(target=hud_writer, daemon=True)
t1.start()
t2.start()

# Keep main thread alive
while True:
    time.sleep(1)
