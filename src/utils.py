import cv2
import os
from datetime import datetime, timezone

def read_image_bgr(path):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(path)
    return img

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def timestamp():
    return datetime.now(timezone.utc).isoformat()
