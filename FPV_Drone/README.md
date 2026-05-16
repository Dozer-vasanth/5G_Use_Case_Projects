For this project we build a custom FPV drone system that delivers an immersive real-time first-person perspective through a VR headset over 5G networks. The existing infrastructure with iDronam for flying the drone works reliably and handles dynamic Internet Protocol (IP) addressing automatically. To reduce long-term costs (since Idronum is subscription based), improve flexibility, and gain full control, we propose transitioning to a complete open-source stack.

After you connect your drone to QGroundControl and setup MAVLink connection (for which the instructions are present in the pdf report) you can run hud_overlay.py to get important telemetries like battery percentage and flight mode which will then be saved in hud_data.txt (created by the code).

The data inside hud_data.txt will then be overlayed on the drone's video feed with the help of ffmpeg. The command is ffmpeg -rtsp_transport tcp -i rtsp://drone_ip:10000/drone_cam -vf "drawtext=textfile=hud_data.txt:reload=1:fontcolor=white:fontsize=36:box=1:boxcolor=black@0.6:x=20:y=20" -c:v libx264 -preset ultrafast -tune zerolatency -f rtsp rtsp://localhost:8554/fpv_hud
Mediamtx is used to create a local server which then retransmits the video feed with all the important telemetries overlayed on top.
More information about installation and configuration of Mediamtx and FFmpeg can be found in the pdf report. 

<img width="1600" height="738" alt="telemetriesOverlay" src="https://github.com/user-attachments/assets/a2f0ccef-736e-4a2c-8536-1735c888a1db" />
