import os
import time
import subprocess
import cv2
import glob
import shutil

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

CAPTURE_INTERVAL = 1.0  
MAX_FRAMES = 10         
LIVE_DIR = "live_data"
DATA_DIR = "data"   
STATE_FILE = "system_state.txt"

def setup_live_environment():
    os.makedirs(LIVE_DIR, exist_ok=True)
    mappings = ['parking_zones.json', 'road_network.json', 'runtime_points.json']
    for file in mappings:
        src = os.path.join(DATA_DIR, file)
        dst = os.path.join(LIVE_DIR, file)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy(src, dst)

def read_state():
    if not os.path.exists(STATE_FILE): return "static"
    with open(STATE_FILE, "r") as f: return f.read().strip()

if __name__ == "__main__":
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w") as f: f.write("static")

    # --- THE SUPERVISOR LOOP ---
    # This keeps the script running and reboots Flask whenever you click a mode button
    while True:
        mode = read_state()
        print(f"\n{'='*40}\n>>> BOOTING SYSTEM: {mode.upper()} MODE <<<\n{'='*40}")
        
        env = os.environ.copy()
        if mode == "live":
            setup_live_environment()
            env["PARKING_STREAM_MODE"] = "static" 
            env["PARKING_DATA_DIR"] = LIVE_DIR
            env["PARKING_ZONE_PATH"] = f"{LIVE_DIR}/parking_zones.json"
            env["PARKING_ROAD_PATH"] = f"{LIVE_DIR}/road_network.json"
            env["PARKING_MANUAL_POINTS_PATH"] = f"{LIVE_DIR}/runtime_points.json"
            
            # 1. Start Flask App in the background
            flask_process = subprocess.Popen(["python", "app.py"], env=env)
            
            # # 2. Run Camera Capture in the MAIN thread (Fixes Windows freezing!)
            CAMERA_SOURCE = os.getenv("PARKING_RTSP_URL", "0")

            # 2. Run Camera Capture in the MAIN thread
            # NOTE: Add "/video" to the end of the URL your phone gives you!
            # CAMERA_SOURCE = "http://10.150.61.102:8080/video" # use the ipcamera stream 

            cam_id = int(CAMERA_SOURCE) if str(CAMERA_SOURCE).isdigit() else CAMERA_SOURCE
            
            print(f"[CAMERA] Connecting to source: {cam_id}")
            cap = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW) if isinstance(cam_id, int) else cv2.VideoCapture(cam_id)
            
            # --- NEW BUFFER DRAINING CAPTURE LOOP ---
            frame_counter = 1
            last_save_time = 0
            
            while flask_process.poll() is None: # Run while Flask is alive
                ret, frame = cap.read()
                
                if ret:
                    current_time = time.time()
                    
                    # Only save the frame if CAPTURE_INTERVAL (1.0s) has passed
                    if current_time - last_save_time >= CAPTURE_INTERVAL:
                        filename = os.path.join(LIVE_DIR, f"live_{frame_counter:05d}.jpg")
                        cv2.imwrite(filename, frame)
                        cv2.imwrite(os.path.join(LIVE_DIR, "latest.jpg"), frame)
                        
                        # Cleanup old frames
                        saved_frames = sorted(glob.glob(os.path.join(LIVE_DIR, "live_*.jpg")))
                        if len(saved_frames) > MAX_FRAMES:
                            for old_frame in saved_frames[:-MAX_FRAMES]:
                                os.remove(old_frame)
                        
                        print(f"[CAMERA] Saved {filename}")
                        frame_counter += 1
                        last_save_time = current_time
                        
                else:
                    # If the Wi-Fi connection drops, wait slightly and try again
                    time.sleep(0.1)
            
            print("[CAMERA] Shutting down...")
            cap.release()

        else:
            # --- STATIC MODE ---
            env["PARKING_STREAM_MODE"] = "static"
            env["PARKING_DATA_DIR"] = DATA_DIR
            env["PARKING_ZONE_PATH"] = f"{DATA_DIR}/parking_zones.json"
            env["PARKING_ROAD_PATH"] = f"{DATA_DIR}/road_network.json"
            env["PARKING_MANUAL_POINTS_PATH"] = f"{DATA_DIR}/runtime_points.json"
            
            # Run Flask in the foreground and block until it exits
            subprocess.run(["python", "app.py"], env=env)
        
        # If we reach here, Flask exited (button was clicked). Pause briefly before rebooting.
        time.sleep(1)