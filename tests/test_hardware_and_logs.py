import json

import numpy as np
import pytest

from src import hardware_simulation as hw
from src import logger as lg


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(hw, "STATE_DIR", tmp_path / "hw_state")
    monkeypatch.setattr(lg, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(lg, "IMAGES_DIR", tmp_path / "logs" / "images")
    return tmp_path


def test_importing_does_not_create_folders(tmp_dirs):
    assert not (tmp_dirs / "hw_state").exists()
    assert not (tmp_dirs / "logs").exists()


def test_led_state_is_written(tmp_dirs):
    led = hw.LED("red")
    led.on()
    state = json.loads((tmp_dirs / "hw_state" / "led_red.json").read_text())
    assert state["state"] is True and state["ts"].endswith("+00:00")
    led.off()
    assert json.loads((tmp_dirs / "hw_state" / "led_red.json").read_text())["state"] is False


def test_lcd_keeps_four_lines_and_clears(tmp_dirs):
    lcd = hw.LCD()
    lcd.display(0, "Image: leaf1.jpg")
    lcd.display(7, "ignored")
    assert lcd.lines == ["Image: leaf1.jpg", "", "", ""]
    lcd.clear()
    assert json.loads((tmp_dirs / "hw_state" / "lcd.json").read_text())["lines"] == ["", "", "", ""]


def test_motor_stop_sets_both_wheels_to_zero(tmp_dirs):
    m = hw.MotorDriverSim()
    m.set_speed(120, 80)
    m.stop()
    assert (m.left_speed, m.right_speed) == (0, 0)


def test_detection_log_round_trips(tmp_dirs):
    record = {"source_image": "leaf1.jpg", "alert": "disease",
              "detections": [{"class_name": "Late Blight", "conf": 0.8, "bbox": [1, 2, 3, 4]}]}
    path = lg.save_detection_log(record)
    assert json.loads(path.read_text()) == record


def test_annotated_image_is_saved(tmp_dirs):
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    out = lg.save_annotated_image(img, [{"class_name": "Mold", "conf": 0.6, "bbox": [5, 5, 40, 40]}], "x.jpg")
    assert out.exists() and out.stat().st_size > 0
