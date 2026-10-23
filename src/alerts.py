"""
Turns detections into an alert level for the robot's LEDs, buzzer and LCD.

Healthy detections never raise an alert. A disease seen with low confidence is a
WATCH (yellow), so the farmer can take a closer look; a confident one is a
DISEASE alert (red and buzzer).
"""
from enum import Enum
from typing import Any, Dict, List, Optional


class AlertLevel(Enum):
    OK = "ok"            # nothing found, or only healthy plants
    WATCH = "watch"      # disease detected below the alert threshold
    DISEASE = "disease"  # disease detected at or above the alert threshold


def is_healthy(class_name: Optional[str]) -> bool:
    return bool(class_name) and "healthy" in class_name.lower()


def classify(detections: List[Dict[str, Any]], alert_threshold: float = 0.5) -> AlertLevel:
    """
    detections: list of {class_name, conf, ...} as returned by Detector.predict_image
    alert_threshold: confidence at or above which a disease raises the full alert
    """
    diseases = [d for d in detections if not is_healthy(d.get("class_name"))]
    if not diseases:
        return AlertLevel.OK
    if max(d["conf"] for d in diseases) >= alert_threshold:
        return AlertLevel.DISEASE
    return AlertLevel.WATCH


def top_disease(detections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The most confident disease detection, or None if every detection is healthy."""
    diseases = [d for d in detections if not is_healthy(d.get("class_name"))]
    return max(diseases, key=lambda d: d["conf"]) if diseases else None
