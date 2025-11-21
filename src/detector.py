from ultralytics import YOLO
import cv2
import numpy as np
from typing import List, Dict, Any

class Detector:
    def __init__(self, model_path: str, class_names: List[str]=None, conf: float=0.25):
        """
        model_path: path to .pt model
        class_names: optional list mapping class indices -> names
        conf: confidence threshold
        """
        self.model = YOLO(model_path)
        self.class_names = class_names
        self.conf = conf

    def predict_image(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run detection on a BGR image (numpy).
        Returns list of detections: {class_id, class_name, conf, bbox [x1,y1,x2,y2]}
        """
        results = self.model.predict(source=img, imgsz=640, conf=self.conf, verbose=False)
        # results is list-like, we use results[0]
        out = []
        if len(results) == 0:
            return out
        r = results[0]
        # r.boxes.xyxy, r.boxes.conf, r.boxes.cls
        boxes = getattr(r.boxes, "xyxy", None)
        confs = getattr(r.boxes, "conf", None)
        cls = getattr(r.boxes, "cls", None)
        if boxes is None:
            return out
        for i in range(len(boxes)):
            xy = boxes[i].cpu().numpy().tolist()
            c = int(cls[i].cpu().numpy().item())
            cf = float(confs[i].cpu().numpy().item())
            name = self.class_names[c] if self.class_names and c < len(self.class_names) else str(c)
            out.append({
                "class_id": c,
                "class_name": name,
                "conf": cf,
                "bbox": [float(x) for x in xy]
            })
        return out

    def predict_path(self, img_path: str):
        img = cv2.imread(img_path)
        if img is None:
            raise FileNotFoundError(img_path)
        return self.predict_image(img)
