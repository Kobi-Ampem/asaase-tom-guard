from ultralytics import YOLO
import cv2
import numpy as np
from typing import List, Dict, Any, Optional

class Detector:
    def __init__(self, model_path: str, class_names: Optional[List[str]] = None, conf: float = 0.25):
        """
        model_path: path to .pt model
        class_names: optional override for the class names; by default they come from
                     the model itself, so they always match what it was trained on
        conf: confidence threshold
        """
        self.model = YOLO(model_path)
        self.class_names = class_names or [self.model.names[i] for i in sorted(self.model.names)]
        self.conf = conf

    def predict_image(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run detection on a BGR image (numpy).
        Returns list of detections: {class_id, class_name, conf, bbox [x1,y1,x2,y2]}
        """
        results = self.model.predict(source=img, imgsz=640, conf=self.conf, verbose=False)
        out = []
        if len(results) == 0 or results[0].boxes is None:
            return out
        boxes = results[0].boxes
        for xy, c, cf in zip(boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist()):
            c = int(c)
            out.append({
                "class_id": c,
                "class_name": self.class_names[c] if c < len(self.class_names) else str(c),
                "conf": float(cf),
                "bbox": [float(x) for x in xy]
            })
        return out

    def predict_path(self, img_path: str):
        img = cv2.imread(img_path)
        if img is None:
            raise FileNotFoundError(img_path)
        return self.predict_image(img)
