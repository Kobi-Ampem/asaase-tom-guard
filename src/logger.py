import json
from pathlib import Path
from datetime import datetime
import cv2
import os

LOG_DIR = Path("data") / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR = LOG_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def save_detection_log(detection_record: dict) -> Path:
    """
    detection_record should contain keys like:
    { 'ts':..., 'image': 'filename.jpg', 'model': 'leaf'/'fruit', 'detections': [...] }
    """
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    fname = LOG_DIR / f"log_{ts}.json"
    with open(fname, "w") as f:
        json.dump(detection_record, f, indent=2)
    return fname

def save_annotated_image(image_bgr, detections, out_name=None):
    """
    image_bgr: numpy BGR image
    detections: list of {class_name, conf, bbox}
    """
    if out_name is None:
        out_name = datetime.utcnow().strftime("img_%Y%m%d_%H%M%S_%f.jpg")
    out_path = IMAGES_DIR / out_name
    img = image_bgr.copy()
    for det in detections:
        x1,y1,x2,y2 = map(int, det["bbox"])
        cv2.rectangle(img, (x1,y1), (x2,y2), (0,255,0), 2)
        txt = f'{det["class_name"]}:{det["conf"]:.2f}'
        cv2.putText(img, txt, (x1, max(10,y1-5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
    cv2.imwrite(str(out_path), img)
    return out_path
