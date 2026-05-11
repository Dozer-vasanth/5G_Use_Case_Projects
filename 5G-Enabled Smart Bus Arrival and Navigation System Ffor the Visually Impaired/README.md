# 5G-Enabled Smart Bus Arrival and Navigation System for the Visually Impaired
**Supervisor:** Dr. Salil Kashyap and Aditya Gupta
**Students:** A. Eshanth Reddy (230102005), Ch. SriRam Charan Reddy (230102020)

---

## Overview

This project implements a 5G-enabled smart bus arrival notification system designed to address the transit accessibility gap faced by visually impaired commuters. The system delivers real-time, audio-based arrival alerts without requiring any visual interaction from the user.

An ESP32 microcontroller acquires GPS coordinates and transmits them as JSON payloads over MQTT to a Mosquitto broker hosted on a Multi-access Edge Computing (MEC) server within a 5G laboratory network. A Python-based subscriber applies the Haversine great-circle distance formula to detect when a bus enters a 150-metre geofenced radius around predefined stops, triggering pre-recorded audio announcements accordingly.

The architecture is designed for incremental scalability — from the current single-bus, three-stop prototype to a multi-route, city-scale fleet deployment — without requiring structural redesign of the broker or subscriber logic.

---

## System Architecture

The end-to-end pipeline consists of five asynchronous stages:

1. **Acquisition** — The ESP32 reads NMEA sentences from the NEO-6M GPS module via UART. In the prototype, a static five-point route array is cycled at 0.5 Hz to simulate live GPS data.
2. **Encoding** — Coordinates are serialised into a JSON payload and published to the MQTT topic `smartbus/location` every two seconds.
3. **Brokering** — The Mosquitto broker (hosted at `192.168.116.30:1884`) forwards messages to all active subscribers using QoS 0 delivery semantics.
4. **Detection** — The Python subscriber parses each payload, computes the Haversine distance from the bus to each registered stop, and evaluates the geofence condition.
5. **Output** — Upon geofence entry, the corresponding MP3 audio file is enqueued to a thread-safe audio worker and played without blocking the MQTT event loop.

---

## Hardware Requirements

| Component | Details |
|---|---|
| Microcontroller | ESP32 (Espressif Systems), dual-core 240 MHz, integrated Wi-Fi |
| GPS Module | u-blox NEO-6M, NMEA 0183 over UART at 9600 baud, 2.5 m CEP accuracy |
| Network | Laboratory Wi-Fi (prototype) / 5G cellular with MEC (deployment) |
| Audio Output | Any system audio device compatible with the `playsound` Python library |

---

## Software Requirements

### ESP32 Firmware (Arduino / PlatformIO)

- [Arduino core for ESP32](https://github.com/espressif/arduino-esp32)
- [PubSubClient](https://github.com/knolleary/pubsubclient) — MQTT client library
- [TinyGPS++](https://github.com/mikalhart/TinyGPSPlus) — NMEA sentence parser (required for live GPS integration)
- [ArduinoJson](https://arduinojson.org/) — JSON payload serialisation

### Python Subscriber

- Python 3.8 or later
- `paho-mqtt` — MQTT client
- `playsound` — Audio playback
- `math` (standard library) — Haversine computation

Install Python dependencies:

```bash
pip install paho-mqtt playsound
```

### MQTT Broker

- [Mosquitto](https://mosquitto.org/) installed and running on the MEC server or local machine.

---

## Repository Structure

```
5G_Use_Case_Projects/
└── 5G-Enabled Smart Bus Arrival and Navigation System for the Visually Impaired/
    ├── esp32_firmware/          # Arduino sketch for the ESP32 publisher
    ├── python_subscriber/       # Python geofence detection and audio alert script
    ├── audio/                   # Pre-recorded MP3 announcement files for each stop
    └── README.md                # Project-level documentation
```

---

## Configuration

### ESP32 Firmware

Open the Arduino sketch and update the following constants to match your network environment:

```cpp
const char* ssid         = "YOUR_WIFI_SSID";
const char* password     = "YOUR_WIFI_PASSWORD";
const char* mqtt_server  = "192.168.116.30";   // IP address of the Mosquitto broker
const int   mqtt_port    = 1884;
const char* topic        = "smartbus/location";
```

The JSON payload published on each cycle is structured as follows:

```json
{
  "bus_id": "BUS_01",
  "lat": 26.192345,
  "lon": 91.699876,
  "time": 1024
}
```
## Execution Instructions

### Step 1 — Start the Mosquitto Broker

On the MEC server or local machine:

```bash
mosquitto -v -p 1884
```

### Step 2 — Flash the ESP32 Firmware

1. Open the sketch in the Arduino IDE or PlatformIO.
2. Set the correct board: **ESP32 Dev Module**.
3. Update the Wi-Fi credentials and broker IP as described in the Configuration section.
4. Compile and upload to the ESP32.
5. Open the Serial Monitor at 115200 baud to verify MQTT connection and publish activity.

### Step 3 — Run the Python Subscriber

Navigate to the `python_subscriber/` directory and execute:

```bash
python subscriber.py
```

The subscriber will connect to the broker, begin consuming location messages, and play the appropriate audio announcement each time the bus enters a registered stop's geofence.

### Step 4 — Verify Operation

Monitor the Serial output of the ESP32 and the terminal output of the Python subscriber. Expected behaviour:

- ESP32 publishes a JSON payload every two seconds.
- Python subscriber logs computed Haversine distances to each stop.
- Audio announcement plays once on geofence entry; repeated alerts are suppressed while the bus dwells within the stop radius.

---

## Planned Enhancements

- Integration of the NEO-6M GPS module via UART to replace the simulated route with live NMEA data.
- Replacement of the Wi-Fi last-hop link with a 5G cellular module (Quectel RM500Q-GL).
- TLS 1.3 encryption and certificate-based MQTT authentication for production security.
- Predictive ETA computation using a rolling average speed model.
- Mobile application with Bluetooth earphone audio for on-person use.
- Persistent time-series database (InfluxDB) for trip analytics.

---

## Demonstration Videos

- [Demo Video 1](https://drive.google.com/file/d/1HaAxhDUBzomsqaR77nC7LFvBO0EdvRGW/view?usp=drivesdk)
- [Demo Video 2](https://drive.google.com/file/d/1w946QUGjj3drpf898rb8xkP3_4Qfp31i/view?usp=drivesdk)
