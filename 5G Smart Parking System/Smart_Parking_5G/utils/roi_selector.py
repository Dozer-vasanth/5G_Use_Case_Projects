import cv2
import json
import os
import numpy as np
import math
import sys

# --- DYNAMIC MODE SWITCH ---
# Read the mode from the command line (defaults to static)
target_mode = sys.argv[1] if len(sys.argv) > 1 else "static"
print(f"Launching Calibrator in {target_mode.upper()} mode...")

DATA_DIR = "live_data" if target_mode == "live" else "data"
os.makedirs(DATA_DIR, exist_ok=True)

IMAGE_SOURCE = os.path.join(DATA_DIR, "live_baseline.jpg" if target_mode == "live" else "baseline.png") 
JSON_SLOTS = os.path.join(DATA_DIR, 'parking_zones.json')
JSON_ROADS = os.path.join(DATA_DIR, 'road_network.json')
JSON_POINTS = os.path.join(DATA_DIR, 'runtime_points.json')

mode = "SLOTS"  
# Data Storage
points, slots = [], {}
slot_count = 1
nodes, edges = {}, []
node_count = 1
active_node, hover_node = None, None
mouse_x, mouse_y = 0, 0
entry_point, exit_point = None, None # NEW: Global points

# --- LOAD EXISTING DATA ---
if os.path.exists(JSON_SLOTS):
    try:
        with open(JSON_SLOTS, 'r') as f:
            slots = json.load(f)
            slot_nums = [int(k.split('_')[1]) for k in slots.keys() if '_' in k]
            slot_count = max(slot_nums) + 1 if slot_nums else 1
    except: pass

if os.path.exists(JSON_ROADS):
    try:
        with open(JSON_ROADS, 'r') as f:
            road_data = json.load(f)
            nodes = road_data.get("nodes", {})
            edges = road_data.get("edges", [])
            node_nums = [int(k.split('_')[1]) for k in nodes.keys() if '_' in k]
            node_count = max(node_nums) + 1 if node_nums else 1
    except: pass

if os.path.exists(JSON_POINTS):
    try:
        with open(JSON_POINTS, 'r') as f:
            pts_data = json.load(f)
            entry_point = pts_data.get("entry_point")
            exit_point = pts_data.get("exit_point")
    except: pass

def get_nearest_node(x, y, threshold=15):
    for n_id, pt in nodes.items():
        if math.hypot(pt[0]-x, pt[1]-y) < threshold: return n_id
    return None

HEADER_HEIGHT = 140 

def mouse_callback(event, x, y, flags, param):
    global points, slots, slot_count, nodes, edges, node_count, active_node
    global mouse_x, mouse_y, hover_node, entry_point, exit_point

    y = y - HEADER_HEIGHT
    if y < 0: return 

    if event == cv2.EVENT_MOUSEMOVE:
        mouse_x, mouse_y = x, y
        hover_node = get_nearest_node(x, y)

    if mode == "SLOTS":
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4: points.append([x, y])
        elif event == cv2.EVENT_RBUTTONDOWN:
            if points: points.pop()
            else:
                slot_to_delete = None
                for slot_id, pts in slots.items():
                    if cv2.pointPolygonTest(np.array(pts, np.int32), (x, y), False) >= 0:
                        slot_to_delete = slot_id; break
                if slot_to_delete: del slots[slot_to_delete]

    elif mode == "ROADS":
        if event == cv2.EVENT_LBUTTONDOWN:
            if hover_node:
                if active_node and active_node != hover_node:
                    edge = sorted([active_node, hover_node])
                    if edge not in edges: edges.append(edge)
                active_node = hover_node
            else:
                new_node_id = f"N_{node_count}"
                nodes[new_node_id] = [x, y]
                node_count += 1
                if active_node: edges.append(sorted([active_node, new_node_id]))
                active_node = new_node_id
        elif event == cv2.EVENT_RBUTTONDOWN:
            if active_node: active_node = None 
            elif hover_node:
                del nodes[hover_node]
                edges[:] = [e for e in edges if hover_node not in e]
                hover_node = None
                
    # NEW: Entry and Exit Point Logic
    elif mode == "ENTRY" and event == cv2.EVENT_LBUTTONDOWN:
        entry_point = [x, y]
    elif mode == "EXIT" and event == cv2.EVENT_LBUTTONDOWN:
        exit_point = [x, y]

frame = cv2.imread(IMAGE_SOURCE)
if frame is None:
    print(f"Error: Could not read '{IMAGE_SOURCE}'. Capture a baseline first!")
    exit()

window_name = "Smart Parking - Mapping Tool"

# --- DYNAMIC WINDOW SIZING ---
if target_mode == "static":
    # Static images are huge; allow shrinking but keep aspect ratio
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(window_name, 1280, 720)
else:
    # Live webcam frames are smaller; use 1:1 pixel sizing
    # cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(window_name, 1280, 720)

cv2.setMouseCallback(window_name, mouse_callback)

while True:
    canvas = frame.copy()
    header = np.zeros((HEADER_HEIGHT, frame.shape[1], 3), dtype=np.uint8)
    font_scale = 0.55 if frame.shape[1] < 800 else 0.7
    
    # UI Header Text
    cv2.putText(header, f"MODE: {mode}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(header, "KEYS: 'M'=Slots/Roads | 'E'=Entry | 'X'=Exit", (180, 30), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (200, 200, 200), 1, cv2.LINE_AA)
    
    if mode == "SLOTS":
        cv2.putText(header, "MOUSE: [Left] Add dot | [Right] Delete dot/Slot", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(header, "'S' -> Save Slot | 'U' -> Undo", (10, 95), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), 1, cv2.LINE_AA)
    elif mode == "ROADS":
        cv2.putText(header, "MOUSE: [Left] Connect | [Right] Break/Delete", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(header, f"Active: {active_node or 'None'}", (10, 95), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 165, 255), 2, cv2.LINE_AA)
    elif mode == "ENTRY":
        cv2.putText(header, "MOUSE: [Left Click] to set the ENTRY point (Magenta)", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 0, 255), 1, cv2.LINE_AA)
    elif mode == "EXIT":
        cv2.putText(header, "MOUSE: [Left Click] to set the EXIT point (Orange)", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 165, 255), 1, cv2.LINE_AA)

    cv2.putText(header, "PRESS 'Q' TO SAVE ALL SETTINGS AND QUIT", (10, 125), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), 2, cv2.LINE_AA)

    # DRAW SLOTS
    for slot_id, pts in slots.items():
        pts_array = np.array(pts, np.int32) 
        cv2.polylines(canvas, [pts_array], isClosed=True, color=(0, 255, 0), thickness=2)
        cx, cy = int(np.mean([p[0] for p in pts])), int(np.mean([p[1] for p in pts]))
        cv2.putText(canvas, slot_id, (cx-20, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
    for pt in points: cv2.circle(canvas, tuple(pt), 6, (0, 255, 255), -1) 
    if len(points) > 0:
        cv2.polylines(canvas, [np.array(points, np.int32)], isClosed=(len(points)==4), color=(0, 255, 0) if len(points)==4 else (0,0,255), thickness=2)

    # DRAW ROADS
    for edge in edges:
        cv2.line(canvas, tuple(nodes[edge[0]]), tuple(nodes[edge[1]]), (255, 255, 0), 2, cv2.LINE_AA) 
    if mode == "ROADS" and active_node:
        cv2.line(canvas, tuple(nodes[active_node]), (mouse_x, mouse_y), (255, 255, 255), 1, cv2.LINE_AA)
    for n_id, pt in nodes.items():
        cv2.circle(canvas, tuple(pt), 8 if n_id in (hover_node, active_node) else 5, (0, 0, 255) if n_id == active_node else (0, 255, 0) if n_id == hover_node else (255, 255, 0), -1)

    # DRAW ENTRY / EXIT POINTS
    if entry_point:
        cv2.circle(canvas, tuple(entry_point), 10, (255, 0, 255), -1)
        cv2.putText(canvas, "ENTRY", (entry_point[0]-25, entry_point[1]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    if exit_point:
        cv2.circle(canvas, tuple(exit_point), 10, (0, 165, 255), -1)
        cv2.putText(canvas, "EXIT", (exit_point[0]-20, exit_point[1]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

    display_frame = cv2.vconcat([header, canvas])
    cv2.imshow(window_name, display_frame)
    
    key = cv2.waitKey(1) & 0xFF
    if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1: break

    # Keyboard Toggles
    if key == ord('m'): 
        mode = "ROADS" if mode == "SLOTS" else "SLOTS"
        points, active_node = [], None 
    elif key == ord('e'): mode = "ENTRY"
    elif key == ord('x'): mode = "EXIT"
    elif key == ord('s') and mode == "SLOTS" and len(points) == 4:
        slots[f"Slot_{slot_count}"] = points.copy()
        slot_count += 1
        points = [] 
    elif key == ord('u') and mode == "SLOTS":
        if slot_count > 1:
            slot_count -= 1
            slots.pop(f"Slot_{slot_count}", None)
    elif key == ord('c') and mode == "ROADS":
        nodes.clear(); edges.clear(); active_node = None
    elif key == ord('q'): break

# --- SAVE EVERYTHING ON QUIT ---
print("\n--- SAVING CALIBRATION DATA ---")
try:
    with open(JSON_SLOTS, 'w') as f: json.dump(slots, f, indent=4)
    with open(JSON_ROADS, 'w') as f: json.dump({"nodes": nodes, "edges": edges}, f, indent=4)
    
    # Save the new Entry and Exit points!
    with open(JSON_POINTS, 'r') as f: current_points = json.load(f)
    if entry_point: current_points["entry_point"] = entry_point
    if exit_point: current_points["exit_point"] = exit_point
    with open(JSON_POINTS, 'w') as f: json.dump(current_points, f, indent=4)
    
    print("✅ Successfully saved Slots, Roads, and Entry/Exit points.")
except Exception as e: print(f"❌ ERROR SAVING FILES: {e}")

cv2.destroyAllWindows()