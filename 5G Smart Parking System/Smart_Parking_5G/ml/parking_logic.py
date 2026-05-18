import cv2
import numpy as np
import math

# Feature 4: Temporal smoothing + Unknown state for stable slot status
class SlotStateSmoother:
    def __init__(self, enter_confirm_frames=3, exit_confirm_frames=5, unknown_timeout_frames=20):
        self.enter_confirm_frames = enter_confirm_frames
        self.exit_confirm_frames = exit_confirm_frames
        self.unknown_timeout_frames = unknown_timeout_frames
        self.last_stable = {}
        self.candidate = {}
        self.candidate_count = {}
        self.frames_since_seen = {}

    def update(self, raw_status):
        stable_status = {}
        for slot_id, current in raw_status.items():
            if slot_id not in self.last_stable:
                self.last_stable[slot_id] = "Free"
                self.candidate[slot_id] = current
                self.candidate_count[slot_id] = 1
                self.frames_since_seen[slot_id] = 0

            if current in ("Occupied", "Obstacle"):
                self.frames_since_seen[slot_id] = 0
            else:
                self.frames_since_seen[slot_id] += 1

            if current == self.last_stable[slot_id]:
                self.candidate_count[slot_id] = 0
            else:
                if self.candidate.get(slot_id) != current:
                    self.candidate[slot_id] = current
                    self.candidate_count[slot_id] = 1
                else:
                    self.candidate_count[slot_id] += 1

                confirm_needed = self.enter_confirm_frames if current in ("Occupied", "Obstacle") else self.exit_confirm_frames
                if self.candidate_count[slot_id] >= confirm_needed:
                    self.last_stable[slot_id] = current
                    self.candidate_count[slot_id] = 0

            # Feature 11: Uncertain/Unknown slot state under prolonged uncertainty
            if self.frames_since_seen[slot_id] >= self.unknown_timeout_frames and self.last_stable[slot_id] in ("Occupied", "Obstacle"):
                stable_status[slot_id] = "Unknown"
            else:
                stable_status[slot_id] = self.last_stable[slot_id]

        return stable_status


def check_parking_status(detections, parking_zones):
    status = {slot_id: "Free" for slot_id in parking_zones.keys()}
    aisle_vehicles = [] # Track cars driving in the lanes
    slot_polygons = {slot_id: np.array(points, np.int32) for slot_id, points in parking_zones.items()}
    
    for box in detections:
        x1, y1, x2, y2, class_id = box
        center_x = int((x1 + x2) / 2)
        center_y = int(y2 - ((y2 - y1) * 0.1)) 
        
        # Feature 21: Best-slot assignment to reduce false occupancy on neighboring slots
        best_slot = None
        best_score = 0.0
        for slot_id, points in parking_zones.items():
            pts_array = slot_polygons[slot_id]
            anchor_bottom = (center_x, center_y)
            anchor_left = (int(x1 + 0.25 * (x2 - x1)), int(y2 - 0.15 * (y2 - y1)))
            anchor_right = (int(x1 + 0.75 * (x2 - x1)), int(y2 - 0.15 * (y2 - y1)))

            inside_hits = sum(
                1
                for p in (anchor_bottom, anchor_left, anchor_right)
                if cv2.pointPolygonTest(pts_array, p, False) >= 0
            )

            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            slot_x1, slot_y1 = min(x_coords), min(y_coords)
            slot_x2, slot_y2 = max(x_coords), max(y_coords)
            inter_x1 = max(x1, slot_x1)
            inter_y1 = max(y1, slot_y1)
            inter_x2 = min(x2, slot_x2)
            inter_y2 = min(y2, slot_y2)
            inter_w = max(0, inter_x2 - inter_x1)
            inter_h = max(0, inter_y2 - inter_y1)
            inter_area = inter_w * inter_h
            box_area = max(1, (x2 - x1) * (y2 - y1))
            overlap_ratio = inter_area / box_area

            score = (inside_hits / 3.0) * 0.7 + overlap_ratio * 0.3
            if score > best_score:
                best_score = score
                best_slot = slot_id

        # Feature 35: Slightly lower slot lock threshold for angled-camera parked vehicles
        is_parked = best_slot is not None and best_score >= 0.28
        if is_parked:
            if class_id in [15, 16]:
                status[best_slot] = "Obstacle"
            else:
                status[best_slot] = "Occupied"

        # If the car isn't in any parking slot, it's driving in the aisle
        if not is_parked and class_id in [2, 3, 5, 7]: # Car, Moto, Bus, Truck
            aisle_vehicles.append((center_x, center_y))

    return status, aisle_vehicles

# UPGRADE: Added claimed_slots parameter to prevent double-booking
def find_nearest_free_slot(parking_status, parking_zones, vehicle_point, claimed_slots=None):
    if claimed_slots is None:
        claimed_slots = set()
        
    min_dist = float('inf')
    nearest_slot = None
    nearest_center = None

    for slot_id, status in parking_status.items():
        # Only check slots that are Free AND haven't been claimed by another car yet
        if status == "Free" and slot_id not in claimed_slots:
            pts = parking_zones[slot_id]
            center_x = int(sum([p[0] for p in pts]) / len(pts))
            center_y = int(sum([p[1] for p in pts]) / len(pts))
            
            dist = math.sqrt((center_x - vehicle_point[0])**2 + (center_y - vehicle_point[1])**2)
            
            if dist < min_dist:
                min_dist = dist
                nearest_slot = slot_id
                nearest_center = (center_x, center_y)

    return nearest_slot, nearest_center