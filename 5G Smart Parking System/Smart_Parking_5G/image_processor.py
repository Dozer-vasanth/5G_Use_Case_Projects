import cv2
import json
import numpy as np
import math
from ultralytics import YOLO
from ml.parking_logic import check_parking_status, find_nearest_free_slot

model = YOLO('ml/yolov8n.pt') 
TARGET_CLASSES = [2, 3, 5, 7, 15, 16]

# UPDATED COORDINATES BASED ON YOUR PHOTO
ENTRY_POINT = (400, 750) 
EXIT_POINT = (200, 750)  

def load_zones(filepath='data/parking_zones.json'):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content: return {}
            return json.loads(content)
    except Exception:
        return {}

def process_static_image(image_path):
    zones = load_zones()
    frame = cv2.imread(image_path)
    if frame is None: return None

    results = model(frame, classes=TARGET_CLASSES, verbose=False)[0]
    detections = [[int(x1), int(y1), int(x2), int(y2), int(cls)] for x1, y1, x2, y2, conf, cls in results.boxes.data.tolist()]

    # Feature 19: Keep static-mode logic aligned with upgraded slot logic
    slot_status, aisle_vehicles = check_parking_status(detections, zones)

    # Draw Parking Slots
    for slot_id, pts in zones.items():
        pts_array = np.array(pts, np.int32)
        status = slot_status[slot_id]
        color = (0, 255, 0) if status == "Free" else (0, 0, 255) if status == "Occupied" else (0, 255, 255) if status == "Obstacle" else (128, 128, 128)
        
        cv2.polylines(frame, [pts_array], isClosed=True, color=color, thickness=2)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts_array], color)
        cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
        cv2.putText(frame, slot_id, tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

    # Draw Entry and Exit markers
    cv2.circle(frame, ENTRY_POINT, 8, (255, 0, 255), -1)
    cv2.putText(frame, "ENTRY", (ENTRY_POINT[0]-20, ENTRY_POINT[1]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,0,255), 2)
    cv2.circle(frame, EXIT_POINT, 8, (0, 165, 255), -1) # Orange
    cv2.putText(frame, "EXIT", (EXIT_POINT[0]-20, EXIT_POINT[1]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,165,255), 2)

    # Dynamic Routing for moving cars
    for vehicle_point in aisle_vehicles:
        # Distance to entry gate
        dist_to_entry = math.sqrt((vehicle_point[0] - ENTRY_POINT[0])**2 + (vehicle_point[1] - ENTRY_POINT[1])**2)
        
        if dist_to_entry < 200: # Car is entering
            nearest_slot, target_center = find_nearest_free_slot(slot_status, zones, vehicle_point)
            if nearest_slot:
                cv2.arrowedLine(frame, vehicle_point, target_center, (255, 255, 0), 4, tipLength=0.05)
                cv2.putText(frame, f"Routing to {nearest_slot}", (vehicle_point[0], vehicle_point[1]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        else: # Car is exiting
            cv2.arrowedLine(frame, vehicle_point, EXIT_POINT, (0, 165, 255), 4, tipLength=0.05)
            cv2.putText(frame, "Routing to EXIT", (vehicle_point[0], vehicle_point[1]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

    ret, buffer = cv2.imencode('.jpg', frame)
    return buffer.tobytes()