"""
Stand-ins for the robot's LEDs, buzzer, LCD and motor driver, so the pipeline runs on
a laptop. Each device prints what it would do and writes its state to
data/hw_state/<device>.json. On the robot, the same calls drove the real parts.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path("data") / "hw_state"

def _save(name: str, payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload["ts"] = datetime.now(timezone.utc).isoformat()
    (STATE_DIR / f"{name}.json").write_text(json.dumps(payload))

class LED:
    def __init__(self, color):
        self.color = color
        self.state = False
    def on(self):
        self.state = True
        print(f"[LED-{self.color}] ON")
        _save(f"led_{self.color}", {"color": self.color, "state": self.state})
    def off(self):
        self.state = False
        print(f"[LED-{self.color}] OFF")
        _save(f"led_{self.color}", {"color": self.color, "state": self.state})

class Buzzer:
    def beep(self, duration_ms=200):
        print(f"[BUZZER] Beep {duration_ms}ms")
        _save("buzzer", {"beep_ms": duration_ms})

class LCD:
    def __init__(self):
        self.lines = [""]*4
    def display(self, line:int, text:str):
        if 0 <= line < 4:
            self.lines[line] = text
        print("[LCD] " + " | ".join(self.lines))
        _save("lcd", {"lines": self.lines})
    def clear(self):
        self.lines = [""]*4
        _save("lcd", {"lines": self.lines})

class MotorDriverSim:
    def __init__(self):
        self.left_speed = 0
        self.right_speed = 0
    def set_speed(self, left:int, right:int):
        self.left_speed = left
        self.right_speed = right
        print(f"[MOTOR] L={left} R={right}")
        _save("motors", {"left": left, "right": right})
    def stop(self):
        self.set_speed(0,0)
