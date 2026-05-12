import os
# This must come BEFORE 'import cv2'
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2

url = "rtsp://admin:admin123@12.0.0.89:554/avstream/channel=1/stream=1.sdp"
cap = cv2.VideoCapture(url)

# Add a shorter timeout for testing
cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)

if not cap.isOpened():
    print("Connection failed: Stream timed out again.")
else:
    print("Connection successful!")