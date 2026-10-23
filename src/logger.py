import json
from pathlib import Path
from datetime import datetime, timezone
import cv2

LOG_DIR = Path("data") / "logs"
IMAGES_DIR = LOG_DIR / "images"

def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

def save_detection_log(detection_record: dict) -> Path:
    """
    detection_record should contain keys like:
    { 'ts':..., 'source_image': 'filename.jpg', 'alert': 'ok'/'watch'/'disease', 'detections': [...] }
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fname = LOG_DIR / f"log_{_stamp()}.json"
    with open(fname, "w") as f:
        json.dump(detection_record, f, indent=2)
    return fname

def save_annotated_image(image_bgr, detections, out_name=None):
    """
    image_bgr: numpy BGR image
    detections: list of {class_name, conf, bbox}
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if out_name is None:
        out_name = f"img_{_stamp()}.jpg"
    out_path = IMAGES_DIR / out_name
    img = image_bgr.copy()
    for det in detections:
        x1,y1,x2,y2 = map(int, det["bbox"])
        cv2.rectangle(img, (x1,y1), (x2,y2), (0,255,0), 2)
        txt = f'{det["class_name"]}:{det["conf"]:.2f}'
        cv2.putText(img, txt, (x1, max(10,y1-5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
    cv2.imwrite(str(out_path), img)
    return out_path
