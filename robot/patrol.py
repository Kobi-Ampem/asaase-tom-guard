"""
The robot's job along a row: drive a short segment, stop, let the chassis settle,
photograph the plant, detect disease, alert, log, and move on.

    ADVANCE ──> SETTLE ──> INSPECT ──> (next station) ... ──> DONE
       │ obstacle
       └──> WAIT, retry up to max_retries ──> BLOCKED (row ends)

The Arduino stops the robot by itself at an obstacle; this loop decides what to do next.
While driving, the Pi pings every heartbeat_s so the Arduino's watchdog stays satisfied.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from robot.base import ArduinoBase
from src.alerts import AlertLevel, top_disease

ALERT_CODES = {AlertLevel.OK: 0, AlertLevel.WATCH: 1, AlertLevel.DISEASE: 2}


@dataclass
class PatrolConfig:
    stations: int = 10
    speed: int = 150
    segment_ms: int = 1200
    settle_s: float = 0.5
    obstacle_wait_s: float = 2.0
    max_retries: int = 3
    heartbeat_s: float = 0.4


@dataclass
class PatrolResult:
    stations: int = 0
    alerts: Dict[str, int] = field(default_factory=lambda: {lvl.value: 0 for lvl in AlertLevel})
    obstacle_stops: int = 0
    end_reason: str = "done"
    log: List[dict] = field(default_factory=list)


class Patrol:
    def __init__(self, base: ArduinoBase, camera, inspect: Callable[[object], Tuple[AlertLevel, list]],
                 config: PatrolConfig = None, on_station: Callable[[dict], None] = None):
        """
        camera: anything with capture() returning a BGR image
        inspect: image -> (AlertLevel, detections)
        on_station: optional callback with each station's record (for logging)
        """
        self.base = base
        self.camera = camera
        self.inspect = inspect
        self.cfg = config or PatrolConfig()
        self.on_station = on_station
        self.clock = base.clock

    def run(self) -> PatrolResult:
        result = PatrolResult()
        self.base.alert(0)
        self.base.lcd(0, "AsaaseTom Guard")
        try:
            for station in range(1, self.cfg.stations + 1):
                if not self._advance(result):
                    result.end_reason = "blocked"
                    break
                self.clock.sleep(self.cfg.settle_s)
                self._inspect(station, result)
                result.stations = station
        finally:
            self.base.stop()
        self.base.lcd(3, f"Done: {result.stations} plants")
        return result

    def _advance(self, result: PatrolResult) -> bool:
        """Drive one segment. False if an obstacle stays in the way after every retry."""
        for attempt in range(self.cfg.max_retries + 1):
            if self.base.poll().blocked:
                result.obstacle_stops += 1
                self.base.lcd(2, "Obstacle: waiting")
                self.clock.sleep(self.cfg.obstacle_wait_s)
                continue
            if self._drive_segment():
                return True
            result.obstacle_stops += 1
            self.base.lcd(2, "Obstacle: waiting")
            self.clock.sleep(self.cfg.obstacle_wait_s)
        return False

    def _drive_segment(self) -> bool:
        """True if the segment finished, False if the obstacle reflex stopped it."""
        self.base.drive(self.cfg.speed, self.cfg.speed, self.cfg.segment_ms)
        end = self.clock.now() + self.cfg.segment_ms / 1000
        while self.clock.now() < end:
            self.clock.sleep(min(self.cfg.heartbeat_s, end - self.clock.now()))
            if self.base.poll().blocked:
                self.base.stop()
                return False
            if self.clock.now() < end:
                self.base.ping()
        return True

    def _inspect(self, station: int, result: PatrolResult) -> None:
        image = self.camera.capture()
        level, detections = self.inspect(image) if image is not None else (AlertLevel.OK, [])
        result.alerts[level.value] += 1
        self.base.alert(ALERT_CODES[level])
        worst = top_disease(detections)
        self.base.lcd(1, f"Plant {station}: {level.value.upper()}")
        self.base.lcd(2, f"{worst['class_name']} {worst['conf']:.0%}" if worst else "")
        t = self.base.telemetry
        record = {"station": station, "alert": level.value, "detections": detections,
                  "temp_c": t.temp_c, "humidity": t.humidity, "camera_ok": image is not None}
        result.log.append(record)
        if self.on_station:
            self.on_station(record)
