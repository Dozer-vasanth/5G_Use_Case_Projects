import heapq
import json
import math
import os
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
import time
from collections import deque
from datetime import datetime

import cv2
import numpy as np
from ultralytics import YOLO

from ml.parking_logic import SlotStateSmoother, check_parking_status, find_nearest_free_slot


# Feature 1: Centralized runtime configuration for production deployment
class RuntimeConfig:
    def __init__(self):
        self.rtsp_url = os.getenv("PARKING_RTSP_URL", "rtsp://admin:admin123@12.0.0.84:554/avstream/channel=1/stream=1.sdp") 
        self.model_path = os.getenv("PARKING_MODEL_PATH", "ml/yolov8n.pt")
        self.zone_path = os.getenv("PARKING_ZONE_PATH", "data/parking_zones.json")
        self.road_path = os.getenv("PARKING_ROAD_PATH", "data/road_network.json") # ADD THIS LINE
        self.stream_mode = os.getenv("PARKING_STREAM_MODE", "rtsp")  # rtsp or static
        self.static_image = os.getenv("PARKING_STATIC_IMAGE", "data/baseline.png")
        self.infer_every_n = int(os.getenv("PARKING_INFER_EVERY_N", "2"))
        self.max_reconnect_attempts = int(os.getenv("PARKING_MAX_RECONNECT", "10"))
        self.reconnect_base_wait_sec = float(os.getenv("PARKING_RECONNECT_BASE_WAIT", "1.0"))
        self.frame_queue_size = int(os.getenv("PARKING_FRAME_QUEUE_SIZE", "8"))
        self.enter_confirm_frames = int(os.getenv("PARKING_ENTER_CONFIRM_FRAMES", "3"))
        self.exit_confirm_frames = int(os.getenv("PARKING_EXIT_CONFIRM_FRAMES", "5"))
        self.unknown_timeout_frames = int(os.getenv("PARKING_UNKNOWN_TIMEOUT_FRAMES", "20"))
        self.entry_point = tuple(json.loads(os.getenv("PARKING_ENTRY_POINT", "[400, 750]")))
        self.exit_point = tuple(json.loads(os.getenv("PARKING_EXIT_POINT", "[200, 750]")))
        self.entry_line = tuple(tuple(v) for v in json.loads(os.getenv("PARKING_ENTRY_LINE", "[[350, 700], [550, 700]]")))
        self.exit_line = tuple(tuple(v) for v in json.loads(os.getenv("PARKING_EXIT_LINE", "[[160, 700], [360, 700]]")))
        self.show_debug = os.getenv("PARKING_SHOW_DEBUG", "1") == "1"
        self.manual_points_path = os.getenv("PARKING_MANUAL_POINTS_PATH", "data/runtime_points.json")
        self.grid_step = int(os.getenv("PARKING_GRID_STEP", "20"))


# Feature 2: Minimal structured logger for ops observability
def log_event(event, **fields):
    payload = {"ts": datetime.utcnow().isoformat() + "Z", "event": event, **fields}
    print(json.dumps(payload))


def load_zones(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception as exc:
        log_event("zones_load_failed", error=str(exc), path=filepath)
        return {}


# Feature 5: Lightweight centroid tracker for frame-to-frame identity continuity
class SimpleTracker:
    def __init__(self, max_distance=80, max_missed=10):
        self.max_distance = max_distance
        self.max_missed = max_missed
        self.next_id = 1
        self.tracks = {}

    def update(self, detections):
        updated = {}
        unmatched_dets = set(range(len(detections)))
        track_ids = list(self.tracks.keys())

        for tid in track_ids:
            tx, ty = self.tracks[tid]["center"]
            best_idx = None
            best_dist = float("inf")
            for idx in unmatched_dets:
                x1, y1, x2, y2, cls = detections[idx]
                cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                dist = math.hypot(cx - tx, cy - ty)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx

            if best_idx is not None and best_dist <= self.max_distance:
                x1, y1, x2, y2, cls = detections[best_idx]
                cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                hist = self.tracks[tid]["history"]
                hist.append((cx, cy))
                updated[tid] = {"center": (cx, cy), "class_id": cls, "missed": 0, "history": hist}
                unmatched_dets.remove(best_idx)
            else:
                self.tracks[tid]["missed"] += 1
                if self.tracks[tid]["missed"] <= self.max_missed:
                    updated[tid] = self.tracks[tid]

        for idx in unmatched_dets:
            x1, y1, x2, y2, cls = detections[idx]
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            updated[self.next_id] = {"center": (cx, cy), "class_id": cls, "missed": 0, "history": deque([(cx, cy)], maxlen=10)}
            self.next_id += 1

        self.tracks = updated
        return self.tracks


def _signed_distance_to_line(point, line):
    (x1, y1), (x2, y2) = line
    px, py = point
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


# Feature 6: Direction estimation using line crossing + motion vector
def detect_direction(track, entry_line, exit_line):
    history = list(track["history"])
    if len(history) < 2:
        return "unknown"

    prev_p = history[-2]
    curr_p = history[-1]
    motion = (curr_p[0] - prev_p[0], curr_p[1] - prev_p[1])

    entry_prev = _signed_distance_to_line(prev_p, entry_line)
    entry_curr = _signed_distance_to_line(curr_p, entry_line)
    exit_prev = _signed_distance_to_line(prev_p, exit_line)
    exit_curr = _signed_distance_to_line(curr_p, exit_line)

    if entry_prev * entry_curr < 0:
        return "entering"
    if exit_prev * exit_curr < 0:
        return "exiting"
    if abs(motion[1]) > abs(motion[0]):
        return "entering" if motion[1] < 0 else "exiting"
    return "unknown"


class StreamEngine:
    def __init__(self, config=None):
        self.config = config or RuntimeConfig()
        self.model = YOLO(self.config.model_path)
        
        # --- TEST MODE: Add '0' (Person) so it detects you as a car ---
        self.target_classes = [0, 2, 3, 5, 7, 15, 16]
        self.vehicle_classes = [0, 2, 3, 5, 7]
        # --------------------------------------------------------------
        
        self.zones = load_zones(self.config.zone_path)
        self.road_nodes, self.road_graph = self._load_road_network(self.config.road_path)
        self._load_manual_points()
        
        # CHANGE THIS:
        # self.road_nodes, self.road_graph = self._load_road_network("data/road_network.json")
        
        # TO THIS:
        self.road_nodes, self.road_graph = self._load_road_network(self.config.road_path)
        
        self._load_manual_points()
        self.tracker = SimpleTracker()
        self.smoother = SlotStateSmoother(
            enter_confirm_frames=self.config.enter_confirm_frames,
            exit_confirm_frames=self.config.exit_confirm_frames,
            unknown_timeout_frames=self.config.unknown_timeout_frames,
        )
        self.health = {
            "status": "starting",
            "last_error": "",
            "fps": 0.0,
            "last_frame_ts": None,
            "reconnect_attempts": 0,
            "free_slots": 0,
            "occupied_slots": 0,
            "unknown_slots": 0,
        }
        self.last_detections = []
        self.last_paths = []
        self.frame_count = 0
        self.last_fps_ts = time.time()

    def reload_data(self):
        """Forces the engine to re-read the JSON files from disk."""
        self.zones = load_zones(self.config.zone_path)
        self.road_nodes, self.road_graph = self._load_road_network(self.config.road_path)
        self._load_manual_points()

    def _load_road_network(self, filepath):
        if not os.path.exists(filepath):
            print(f"Warning: Road network {filepath} not found.")
            return {}, {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("nodes", {})
            edges = data.get("edges", [])
            
            # Build an Adjacency List for fast A* traversal
            graph = {n: [] for n in nodes.keys()}
            for edge in edges:
                n1, n2 = edge[0], edge[1]
                if n1 in graph and n2 in graph:
                    graph[n1].append(n2)
                    graph[n2].append(n1)
            return nodes, graph
        except Exception as exc:
            log_event("road_network_load_failed", error=str(exc))
            return {}, {}

    # Feature 22: Manual entry/exit configuration persisted on disk
    def _load_manual_points(self):
        if not os.path.exists(self.config.manual_points_path):
            return
        try:
            with open(self.config.manual_points_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "entry_point" in data:
                self.config.entry_point = tuple(data["entry_point"])
            if "exit_point" in data:
                self.config.exit_point = tuple(data["exit_point"])
            if "entry_line" in data:
                self.config.entry_line = tuple(tuple(v) for v in data["entry_line"])
            if "exit_line" in data:
                self.config.exit_line = tuple(tuple(v) for v in data["exit_line"])
        except Exception as exc:
            log_event("manual_points_load_failed", error=str(exc))

    def update_manual_points(self, payload):
        if "entry_point" in payload:
            self.config.entry_point = tuple(payload["entry_point"])
        if "exit_point" in payload:
            self.config.exit_point = tuple(payload["exit_point"])
        if "entry_line" in payload:
            self.config.entry_line = tuple(tuple(v) for v in payload["entry_line"])
        if "exit_line" in payload:
            self.config.exit_line = tuple(tuple(v) for v in payload["exit_line"])

        path = self.config.manual_points_path
        
        # FIXED Error 3: Safely create directories avoiding empty path crash
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
            
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "entry_point": list(self.config.entry_point),
                    "exit_point": list(self.config.exit_point),
                    "entry_line": [list(self.config.entry_line[0]), list(self.config.entry_line[1])],
                    "exit_line": [list(self.config.exit_line[0]), list(self.config.exit_line[1])],
                },
                f,
                indent=2,
            )
        return {
            "entry_point": self.config.entry_point,
            "exit_point": self.config.exit_point,
            "entry_line": self.config.entry_line,
            "exit_line": self.config.exit_line,
        }

    def _open_capture(self):
        source = self.config.rtsp_url if self.config.stream_mode == "rtsp" else self.config.static_image
        
        # FIX: If the source is a number (like "0"), convert it to an integer for local webcams
        if isinstance(source, str) and source.isdigit():
            source = int(source)
            
        cap = cv2.VideoCapture(source)
        if self.config.stream_mode == "rtsp":
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    # Feature 7: Robust RTSP reconnect with exponential backoff
    def _read_frame_with_reconnect(self, cap):
        wait = self.config.reconnect_base_wait_sec
        attempts = 0
        while attempts <= self.config.max_reconnect_attempts:
            ok, frame = cap.read()
            if ok and frame is not None:
                self.health["status"] = "running"
                self.health["reconnect_attempts"] = attempts
                return cap, frame

            attempts += 1
            self.health["status"] = "reconnecting"
            self.health["last_error"] = "frame_read_failed"
            log_event("rtsp_read_failed", attempt=attempts)
            time.sleep(wait)
            wait = min(wait * 2, 10.0)
            cap.release()
            cap = self._open_capture()

        self.health["status"] = "degraded"
        return cap, None

    def _run_inference(self, frame):
        # Feature 30: Normalize color channels before inference for PNG/RTSP compatibility
        if frame is None:
            return []
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif len(frame.shape) == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
        # Added conf=0.50 to filter out low-confidence hallucinations
        results = self.model(frame, classes=self.target_classes, conf=0.40, imgsz=640, verbose=False)[0]
        detections = []
        for box in results.boxes.data.tolist():
            x1, y1, x2, y2, _score, class_id = box
            detections.append([int(x1), int(y1), int(x2), int(y2), int(class_id)])
        return detections

    def _draw_yolo_boxes(self, frame, detections):
        """Draws raw YOLO bounding boxes and the physical anchor points for debugging."""
        for box in detections:
            x1, y1, x2, y2, class_id = box
            
            # Draw the raw YOLO bounding box in Pink
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)
            cv2.putText(frame, f"YOLO cls:{class_id}", (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
            
            # Draw the Anchor Points (used for slot assignment)
            center_x = int((x1 + x2) / 2)
            anchor_bottom = (center_x, int(y2 - ((y2 - y1) * 0.05)))
            anchor_middle = (center_x, int(y2 - ((y2 - y1) * 0.20)))
            
            cv2.circle(frame, anchor_bottom, 5, (0, 0, 255), -1) 
            cv2.circle(frame, anchor_middle, 5, (255, 0, 0), -1)

    # Feature 8: Draw multi-state slot overlays including Unknown
    def _draw_slots(self, frame, slot_status):
        for slot_id, pts in self.zones.items():
            pts_array = np.array(pts, np.int32)
            state = slot_status.get(slot_id, "Unknown")
            color = (0, 255, 0)
            if state == "Occupied":
                color = (0, 0, 255)
            elif state == "Obstacle":
                color = (0, 255, 255)
            elif state == "Unknown":
                color = (128, 128, 128)
            cv2.polylines(frame, [pts_array], isClosed=True, color=color, thickness=2)
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts_array], color)
            cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
            cv2.putText(frame, f"{slot_id}:{state}", tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    def _draw_markers(self, frame):
        cv2.circle(frame, self.config.entry_point, 6, (255, 0, 255), -1)
        cv2.putText(frame, "ENTRY", (self.config.entry_point[0] - 20, self.config.entry_point[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)
        cv2.circle(frame, self.config.exit_point, 6, (0, 165, 255), -1)
        cv2.putText(frame, "EXIT", (self.config.exit_point[0] - 20, self.config.exit_point[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
        cv2.line(frame, self.config.entry_line[0], self.config.entry_line[1], (255, 0, 255), 2)
        cv2.line(frame, self.config.exit_line[0], self.config.exit_line[1], (0, 165, 255), 2)

    def _astar_graph(self, start_node, goal_node):
        """Standard A* pathfinding, but traversing nodes/edges instead of pixels."""
        if start_node not in self.road_nodes or goal_node not in self.road_nodes: 
            return []
            
        open_heap = [(0.0, start_node)]
        best_cost = {start_node: 0.0}
        parent = {}
        
        def heuristic(n1, n2):
            p1, p2 = self.road_nodes[n1], self.road_nodes[n2]
            return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

        while open_heap:
            _, curr = heapq.heappop(open_heap)
            if curr == goal_node:
                path = [curr]
                while curr in parent:
                    curr = parent[curr]
                    path.append(curr)
                path.reverse()
                return path
                
            for neighbor in self.road_graph.get(curr, []):
                step_cost = heuristic(curr, neighbor)
                new_cost = best_cost[curr] + step_cost
                if neighbor not in best_cost or new_cost < best_cost[neighbor]:
                    best_cost[neighbor] = new_cost
                    parent[neighbor] = curr
                    heapq.heappush(open_heap, (new_cost + heuristic(neighbor, goal_node), neighbor))
        return []

    def _path_instructions(self, points):
        if len(points) < 2:
            return ["Hold position"]
        instructions = ["Move to lane center"]
        for i in range(1, len(points)):
            dx = points[i][0] - points[i - 1][0]
            dy = points[i][1] - points[i - 1][1]
            if abs(dx) > abs(dy):
                instructions.append("Turn right" if dx > 0 else "Turn left")
            else:
                instructions.append("Go straight" if dy < 0 else "Proceed down-lane")
        instructions.append("Arrive at destination")
        dedup = []
        for text in instructions:
            if not dedup or dedup[-1] != text:
                dedup.append(text)
        return dedup

    def _compute_car_dimensions(self, track):
        history = list(track.get("history", []))
        if len(history) < 2:
            return {"length_px": 0, "width_px": 0}
        spread_x = max(p[0] for p in history) - min(p[0] for p in history)
        spread_y = max(p[1] for p in history) - min(p[1] for p in history)
        return {"length_px": max(20, spread_y + 40), "width_px": max(12, spread_x + 20)}

    def _route_path(self, frame, start_point, end_point, color):
        """
        Stage 1: Snap car to nearest road node
        Stage 2: Graph A* to the node nearest the destination
        Stage 3: Snap from final node to the parking slot
        """
        # FALLBACK: If no road network is loaded, draw a straight Pink line so you know it failed!
        if not self.road_nodes: 
            cv2.line(frame, start_point, end_point, (255, 0, 255), 2)
            return [start_point, end_point], ["Graph missing - driving direct"]
            
        def get_nearest(pt):
            return min(self.road_nodes.keys(), key=lambda n: math.hypot(self.road_nodes[n][0]-pt[0], self.road_nodes[n][1]-pt[1]))
            
        # STAGE 1 & 3: Find the entry/exit nodes on the graph
        start_node = get_nearest(start_point)
        goal_node = get_nearest(end_point)
        
        # STAGE 2: Traverse the road network
        node_path = self._astar_graph(start_node, goal_node)
        
        # FALLBACK: If the graph is disconnected (no path found), draw a straight Pink line
        if not node_path: 
            cv2.line(frame, start_point, end_point, (255, 0, 255), 2)
            return [start_point, end_point], ["Graph disconnected - driving direct"]
            
        # Assemble the final route array
        points = [start_point] + [tuple(self.road_nodes[n]) for n in node_path] + [end_point]
        
        # Draw the route
        for i in range(1, len(points)):
            pt1 = (int(points[i - 1][0]), int(points[i - 1][1]))
            pt2 = (int(points[i][0]), int(points[i][1]))
            cv2.line(frame, pt1, pt2, color, 3)
            
        return points, self._path_instructions(points)

    def _is_vehicle_in_any_slot(self, point):
        px, py = point
        for pts in self.zones.values():
            pts_array = np.array(pts, np.int32)
            if cv2.pointPolygonTest(pts_array, (int(px), int(py)), False) >= 0:
                return True
        return False

    def _draw_guidance(self, frame, stable_status, tracks):
        detailed_paths = []
        free_count = sum(1 for s in stable_status.values() if s == "Free")
        if free_count == 0:
            cv2.putText(frame, "LOT FULL - route to waiting area", (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 3)

        claimed_slots = set()

        for track_id, track in tracks.items():
            if track["class_id"] not in self.vehicle_classes:
                continue
                
            # STRICT INT CASTING (Prevents the crash)
            vehicle_point = (int(track["center"][0]), int(track["center"][1]))
            
            if self._is_vehicle_in_any_slot(vehicle_point):
                continue

            # --- ROUTE 1: NEAREST PARKING SLOT ---
            nearest_slot, target_center = find_nearest_free_slot(stable_status, self.zones, vehicle_point, claimed_slots)
            
            if nearest_slot and target_center:
                claimed_slots.add(nearest_slot)
                
                # Cast the slot center to strict integers
                tc = (int(target_center[0]), int(target_center[1]))
                
                slot_path, slot_steps = self._route_path(frame, vehicle_point, tc, (255, 255, 0))
                
                cv2.circle(frame, tc, 8, (0, 0, 255), -1)
                cv2.putText(frame, f"PARK: {nearest_slot}", (tc[0]-30, tc[1]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                if len(slot_path) >= 2:
                    cv2.arrowedLine(frame, slot_path[-2], slot_path[-1], (255, 255, 0), 3, tipLength=0.05)
                    cv2.putText(frame, f"T{track_id}-> {nearest_slot}", (vehicle_point[0], vehicle_point[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                
                detailed_paths.append({
                    "track_id": track_id,
                    "option": "nearest_slot",
                    "target": nearest_slot,
                    "path": slot_path,
                    "instructions": slot_steps,
                    "car_dimensions": self._compute_car_dimensions(track),
                })

            # --- ROUTE 2: THE EXIT DOOR ---
            exit_pt = (int(self.config.exit_point[0]), int(self.config.exit_point[1]))
            exit_path, exit_steps = self._route_path(frame, vehicle_point, exit_pt, (0, 165, 255))
            
            if len(exit_path) >= 2:
                cv2.arrowedLine(frame, exit_path[-2], exit_path[-1], (0, 165, 255), 3, tipLength=0.05)
                # Offset the exit text slightly downwards so it doesn't overlap the parking text
                cv2.putText(frame, f"T{track_id}-> EXIT", (vehicle_point[0], vehicle_point[1] + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
            
            detailed_paths.append({
                "track_id": track_id,
                "option": "exit",
                "target": "EXIT",
                "path": exit_path,
                "instructions": exit_steps,
                "car_dimensions": self._compute_car_dimensions(track),
            })

        self.last_paths = detailed_paths

    def _update_fps(self):
        now = time.time()
        elapsed = max(1e-6, now - self.last_fps_ts)
        fps = 1.0 / elapsed
        self.health["fps"] = round((self.health["fps"] * 0.9) + (fps * 0.1), 2)
        self.last_fps_ts = now

    def process_frame(self, frame, force_infer=False):
        if frame is None:
            self.health["last_error"] = "empty_frame"
            return None
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif len(frame.shape) == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        self.frame_count += 1
        if force_infer or self.frame_count % max(1, self.config.infer_every_n) == 0 or not self.last_detections:
            detections = self._run_inference(frame)
            self.last_detections = detections
        else:
            detections = self.last_detections

        # FIXED Error 2: Removed duplicate calculation. Compute raw once, update smoother if needed.
        slot_status_raw, _ = check_parking_status(detections, self.zones)
        
        if self.config.stream_mode == "static":
            slot_status = slot_status_raw
        else:
            slot_status = self.smoother.update(slot_status_raw)

        tracks = self.tracker.update(detections)

        self._draw_yolo_boxes(frame, detections)
        self._draw_slots(frame, slot_status)
        self._draw_markers(frame)
        self._draw_guidance(frame, slot_status, tracks)

        self.health["free_slots"] = sum(1 for s in slot_status.values() if s == "Free")
        self.health["occupied_slots"] = sum(1 for s in slot_status.values() if s == "Occupied")
        self.health["unknown_slots"] = sum(1 for s in slot_status.values() if s == "Unknown")
        self.health["last_frame_ts"] = datetime.utcnow().isoformat() + "Z"
        self._update_fps()

        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            self.health["last_error"] = "jpeg_encode_failed"
            return None
        return buffer.tobytes()

   
    def process_image_file(self, image_path):
        # FIX: Wipe memory for ALL static frames so cars don't "teleport" between images.
        # Only preserve tracking history if we are polling the live camera stream.
        if "latest.jpg" not in image_path:
            self.tracker = SimpleTracker() 
            self.last_detections = []
            self.last_paths = []
            # Reset smoother so static frames show occupancy instantly without needing 3 frames of confirmation
            self.smoother = SlotStateSmoother(
                enter_confirm_frames=self.config.enter_confirm_frames,
                exit_confirm_frames=self.config.exit_confirm_frames,
                unknown_timeout_frames=self.config.unknown_timeout_frames,
            )
        
        frame = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if frame is None:
            self.health["last_error"] = f"image_not_found:{image_path}"
            return None
        
        rendered = self.process_frame(frame, force_infer=True)
        if rendered is None:
            return None
        self.health["status"] = "running"
        return rendered

    def generate_frames(self):
        cap = self._open_capture()
        while True:
            cap, frame = self._read_frame_with_reconnect(cap)
            if frame is None:
                time.sleep(0.25)
                continue
            rendered = self.process_frame(frame)
            if not rendered:
                continue
            yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + rendered + b"\r\n")

    def get_health(self):
        return self.health

    # Feature 24: Expose latest detailed guidance for UI/API
    def get_latest_paths(self):
        return self.last_paths  