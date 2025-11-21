import json
from datetime import datetime
from pathlib import Path

STATE_DIR = Path("data") / "hw_state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

class LED:
    def __init__(self, color):
        self.color = color
        self.state = False
    def on(self):
        self.state = True
        print(f"[LED-{self.color}] ON")
        self._save()
    def off(self):
        self.state = False
        print(f"[LED-{self.color}] OFF")
        self._save()
    def _save(self):
        Path(STATE_DIR / f"led_{self.color}.json").write_text(json.dumps({"color": self.color, "state": self.state, "ts": datetime.utcnow().isoformat()}))

class Buzzer:
    def beep(self, duration_ms=200):
        print(f"[BUZZER] Beep {duration_ms}ms")
        Path(STATE_DIR / "buzzer.json").write_text(json.dumps({"beep_ms": duration_ms, "ts": datetime.utcnow().isoformat()}))

class LCD:
    def __init__(self):
        self.lines = [""]*4
    def display(self, line:int, text:str):
        if 0 <= line < 4:
            self.lines[line] = text
        print("[LCD] " + " | ".join(self.lines))
        Path(STATE_DIR / "lcd.json").write_text(json.dumps({"lines": self.lines, "ts": datetime.utcnow().isoformat()}))

class MotorDriverSim:
    def __init__(self):
        self.left_speed = 0
        self.right_speed = 0
    def set_speed(self, left:int, right:int):
        self.left_speed = left
        self.right_speed = right
        print(f"[MOTOR] L={left} R={right}")
        Path(STATE_DIR / "motors.json").write_text(json.dumps({"left": left, "right": right, "ts": datetime.utcnow().isoformat()}))
    def stop(self):
        self.set_speed(0,0)
