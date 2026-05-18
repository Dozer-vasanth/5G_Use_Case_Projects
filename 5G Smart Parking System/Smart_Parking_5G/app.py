from flask import Flask, render_template, Response, request, jsonify
import os
from stream_engine import StreamEngine, RuntimeConfig

app = Flask(__name__)
config = RuntimeConfig()
stream_engine = StreamEngine(config=config)


# Feature 20: Optional API key protection for operational endpoints
def _require_api_key():
    required_key = os.getenv("PARKING_API_KEY", "")
    if not required_key:
        return None
    provided_key = request.headers.get("X-API-Key", "")
    if provided_key != required_key:
        return jsonify({"error": "Unauthorized"}), 401
    return None

@app.route('/')
def index():
    # Pass a flag to the HTML letting it know if we are in Live Mode
    is_live = "true" if os.getenv("PARKING_DATA_DIR") == "live_data" else "false"
    return render_template('index.html', is_live=is_live)

# Feature 3: Static image endpoint now uses unified engine pipeline
# Feature 3: Static image endpoint dynamically checks active directory
# Feature 3: Static image endpoint dynamically checks active directory
@app.route('/process_image')
def process_image():
    image_name = request.args.get('img', 'baseline.png')
    
    is_live = "live" in stream_engine.config.zone_path
    data_dir = "live_data" if is_live else "data"
    image_path = os.path.join(data_dir, image_name)
    
    # --- FALLBACK PROTECTION ---
    if not os.path.exists(image_path):
        # If the requested image isn't ready, serve the baseline so the UI doesn't break
        fallback = os.path.join(data_dir, "live_baseline.jpg" if is_live else "baseline.png")
        if os.path.exists(fallback):
            image_path = fallback
        else:
            return jsonify({"error": f"File not found: {image_path}"}), 404
            
    image_bytes = stream_engine.process_image_file(image_path)
    if image_bytes:
        return Response(image_bytes, mimetype='image/jpeg')
    return f"Error: Could not process {image_path}", 404

# Feature 13: Real RTSP MJPEG endpoint wired to production engine
@app.route('/video_feed')
def video_feed():
    return Response(
        stream_engine.generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )

# Feature 14: Health + readiness + status API
@app.route('/health')
def health():
    unauthorized = _require_api_key()
    if unauthorized:
        return unauthorized
    health_data = stream_engine.get_health()
    code = 200 if health_data.get("status") in ("running", "starting", "reconnecting") else 503
    return jsonify(health_data), code

@app.route('/ready')
def ready():
    unauthorized = _require_api_key()
    if unauthorized:
        return unauthorized
    zones_loaded = bool(stream_engine.zones)
    return jsonify({"ready": zones_loaded}), (200 if zones_loaded else 503)

# Feature 15: Slot summary API for dashboard integration
# Feature 15: Slot summary API for dashboard integration
# Feature 15: Slot summary API for dashboard integration
@app.route('/api/slot_summary')
def slot_summary():
    # 1. Get current health
    health_data = stream_engine.get_health()
    
    # 2. AUTO-WARM: If it's stuck on 'starting', force it to process the active image
    if health_data.get("status") == "starting":
        is_live = "live" in stream_engine.config.zone_path
        data_dir = "live_data" if is_live else "data"
        img_path = os.path.join(data_dir, "latest.jpg" if is_live else "baseline.png")
        
        if os.path.exists(img_path):
            stream_engine.process_image_file(img_path)
            health_data = stream_engine.get_health()

    return jsonify({
        "free_slots": health_data.get("free_slots", 0),
        "occupied_slots": health_data.get("occupied_slots", 0),
        "unknown_slots": health_data.get("unknown_slots", 0),
        "fps": health_data.get("fps", 0.0),
        "status": health_data.get("status", "unknown"),
    })

# Feature 25: API for manual entry/exit updates from dashboard clicks
@app.route('/api/manual_points', methods=['GET', 'POST'])
def manual_points():
    unauthorized = _require_api_key()
    if unauthorized:
        return unauthorized
    if request.method == 'GET':
        return jsonify(
            {
                "entry_point": list(stream_engine.config.entry_point),
                "exit_point": list(stream_engine.config.exit_point),
                "entry_line": [list(stream_engine.config.entry_line[0]), list(stream_engine.config.entry_line[1])],
                "exit_line": [list(stream_engine.config.exit_line[0]), list(stream_engine.config.exit_line[1])],
            }
        )
    payload = request.get_json(silent=True) or {}
    updated = stream_engine.update_manual_points(payload)
    return jsonify(
        {
            "entry_point": list(updated["entry_point"]),
            "exit_point": list(updated["exit_point"]),
            "entry_line": [list(updated["entry_line"][0]), list(updated["entry_line"][1])],
            "exit_line": [list(updated["exit_line"][0]), list(updated["exit_line"][1])],
        }
    )

# Feature 26: API to return detailed route instructions and vehicle dimensions
@app.route('/api/path_details')
def path_details():
    unauthorized = _require_api_key()
    if unauthorized:
        return unauthorized
    return jsonify({"paths": stream_engine.get_latest_paths()})

import shutil
import subprocess

# Feature: Capture current live frame as permanent baseline
@app.route('/api/capture_baseline', methods=['POST'])
def capture_baseline():
    live_dir = os.getenv("PARKING_DATA_DIR", "live_data")
    latest_img = os.path.join(live_dir, "latest.jpg")
    baseline_img = os.path.join(live_dir, "live_baseline.jpg")
    
    if os.path.exists(latest_img):
        shutil.copy(latest_img, baseline_img)
        return jsonify({"status": "success", "message": "Baseline captured!"})
    return jsonify({"error": "No live frames found yet."}), 404

# Feature: Launch the OpenCV drawing tool from the web UI
# Feature: Launch the OpenCV drawing tool from the web UI
# Feature: Launch the OpenCV drawing tool dynamically for the active mode
@app.route('/api/launch_calibrator', methods=['POST'])
def launch_calibrator():
    try:
        # Detect which mode the engine is currently running in
        is_live = "live" in stream_engine.config.zone_path
        target_arg = "live" if is_live else "static"
        
        # Pass the mode argument to the script
        subprocess.run(["python", "utils/roi_selector.py", target_arg])
        
        # Hot-reload the JSONs when the window closes
        stream_engine.reload_data()
        
        return jsonify({"status": "success", "message": f"Calibrated {target_arg} maps."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# Feature: Dynamically switch between Static and Live directories
@app.route('/api/switch_mode', methods=['POST'])
def switch_mode():
    data = request.json or {}
    target = data.get('mode', 'static')
    
    is_live = "live" in stream_engine.config.zone_path
    current_mode = "live" if is_live else "static"
    
    # 1. Do nothing if we are already in the requested mode
    if target == current_mode:
        return jsonify({"status": "ignored", "message": "Already in this mode."})
    
    # 2. Save the requested mode to the state file
    with open("system_state.txt", "w") as f:
        f.write(target)
        
    # 3. Aggressively shut down the Flask server to trigger the reboot in run_system.py
    os._exit(0)

if __name__ == "__main__":
    port = int(os.getenv("PARKING_APP_PORT", "5000"))
    debug = os.getenv("PARKING_DEBUG", "1") == "1"
    app.run(host='0.0.0.0', port=port, debug=debug)