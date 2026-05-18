# Face Image Capture — RetinaFace Edition

Captures frames from your webcam, detects faces using [RetinaFace](https://github.com/serengil/retinaface), crops to each detected face, and saves the crops as JPEG files. Useful for building face recognition datasets or collecting training images.

---

## Requirements

Python 3.8+ and the following packages:

```bash
pip install opencv-python retina-face tf-keras
```

> **Note:** On first run, RetinaFace will download model weights (~1 MB automatically).

---

## Usage

```bash
python capture_face_images.py [OPTIONS]
```

### Basic examples

```bash
# Capture 150 face crops with defaults (live preview on)
python capture_face_images.py

# Capture 300 images, save to a specific folder
python capture_face_images.py -n 300 -o my_dataset

# Capture without a preview window (headless / server use)
python capture_face_images.py --no-preview

# Save crops resized to 224×224 (common for ML training)
python capture_face_images.py --size 224 224

# Use a secondary camera and a lower confidence threshold
python capture_face_images.py -c 1 --threshold 0.75
```

---

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-n`, `--num-images` | `150` | Number of face crops to save |
| `-d`, `--delay` | `0.2` | Minimum seconds between saves |
| `-o`, `--output-dir` | `face_crops_<timestamp>` | Output directory for saved crops |
| `--no-preview` | *(off)* | Disable the live webcam preview window |
| `-c`, `--camera` | `0` | Camera device index (`0` = default webcam) |
| `--threshold` | `0.9` | RetinaFace confidence threshold (0–1) |
| `--padding` | `0.25` | Fractional padding added around the face box |
| `--size W H` | *(no resize)* | Resize saved crops to W×H, e.g. `224 224` |

---

## Output

Crops are saved as high-quality JPEGs (`quality=95`) in the output directory:

```
face_crops_20240518_143022/
├── face_0000.jpg
├── face_0001.jpg
├── face_0002.jpg
└── ...
```

A progress bar is printed to the terminal during capture. Press **`q`** in the preview window to stop early.

---

## How it works

1. Opens the webcam at 640×480.
2. Mirrors each frame horizontally for a natural selfie view.
3. Runs RetinaFace on every frame to detect faces and their bounding boxes.
4. Adds configurable padding around each box and crops the region.
5. Saves each crop once per `--delay` interval until `--num-images` is reached.
6. Optionally displays a live preview with bounding boxes and confidence scores.

---

## Tips

- **Lower `--threshold`** (e.g. `0.75`) if faces aren't being detected in poor lighting.
- **Increase `--padding`** (e.g. `0.4`) to include more context (hair, chin) in each crop.
- **Use `--no-preview`** when running on a headless machine or over SSH.
- **Use `--size 224 224`** to produce crops ready for models like MobileNet or ResNet.
