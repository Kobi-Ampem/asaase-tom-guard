"""
Image sources for the patrol: the Pi camera on the robot, or a folder of photos in simulation.
"""
from itertools import cycle
from pathlib import Path

import cv2


class FolderCamera:
    """Returns the photos in a folder one by one, looping, as if the robot met these plants."""

    def __init__(self, folder: str):
        paths = sorted(p for p in Path(folder).glob("*.*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        if not paths:
            raise FileNotFoundError(f"no images in {folder}")
        self._paths = cycle(paths)
        self.last_path = None

    def capture(self):
        self.last_path = next(self._paths)
        return cv2.imread(str(self.last_path))


class PiCamera:
    """The Raspberry Pi camera through picamera2."""

    def __init__(self, size=(1280, 960)):
        from picamera2 import Picamera2  # only installed on the Pi
        self.cam = Picamera2()
        self.cam.configure(self.cam.create_still_configuration(main={"size": size, "format": "RGB888"}))
        self.cam.start()
        self.last_path = None

    def capture(self):
        # picamera2's "RGB888" is laid out B, G, R in memory, which is what OpenCV expects
        return self.cam.capture_array()
