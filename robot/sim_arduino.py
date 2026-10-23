"""
A Python twin of firmware/tomguard_base/tomguard_base.ino, so the Pi software can be
tested end to end without the robot. It speaks the same protocol and applies the same
safety rules:

- a drive command stops by itself after its duration;
- the watchdog stops the motors if no valid message arrives for WATCHDOG_S
  (the Pi crashed or the cable came loose);
- the obstacle reflex stops forward motion when the ultrasonic reads under STOP_CM.

Keep the constants and rules here in step with the firmware.
"""
import math
from typing import List, Optional

from robot import protocol as p

WATCHDOG_S = 1.0
STOP_CM = 20
TELEMETRY_S = 0.2
MAX_RANGE_CM = 400
FULL_SPEED_CM_S = 30.0  # roughly what a small 4WD chassis does at speed 255


class FakeClock:
    """Simulated time. sleep() advances it in small steps and ticks everything attached."""

    def __init__(self, step: float = 0.01):
        self.t = 0.0
        self.step = step
        self.devices = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        # A whole number of equal steps that lands exactly on the target time; float
        # remainders would otherwise leave callers waiting for a time that never comes.
        end = self.t + seconds
        n = max(1, math.ceil(seconds / self.step - 1e-9))
        dt = seconds / n
        for i in range(1, n + 1):
            self.t = end if i == n else self.t + dt
            for d in self.devices:
                d.tick(self.t, dt)


class SimArduino:
    def __init__(self, clock: FakeClock, obstacle_cm: Optional[float] = None,
                 temp_c: float = 29.5, humidity: float = 71.0):
        self.clock = clock
        clock.devices.append(self)
        self.obstacle_cm = obstacle_cm      # distance from the start of the row, None = clear
        self.position_cm = 0.0
        self.temp_c, self.humidity = temp_c, humidity
        self.left = self.right = 0
        self.drive_until = 0.0
        self.last_msg = 0.0
        self.next_telemetry = 0.0
        self.alert_level = 0
        self.beeps = 0
        self.lcd = [""] * p.LCD_ROWS
        self.outbox: List[bytes] = []
        self.watchdog_stops = 0
        self.reflex_stops = 0

    # --- sensing ---
    def distance_cm(self) -> int:
        if self.obstacle_cm is None:
            return -1
        d = self.obstacle_cm - self.position_cm
        return int(d) if 0 <= d <= MAX_RANGE_CM else -1

    @property
    def moving(self) -> bool:
        return self.left != 0 or self.right != 0

    @property
    def blocked(self) -> bool:
        d = self.distance_cm()
        return 0 <= d < STOP_CM

    # --- the firmware's loop() ---
    def tick(self, t: float, dt: float) -> None:
        if self.moving and t >= self.drive_until:
            self._stop()
        if self.moving and t - self.last_msg > WATCHDOG_S:
            self._stop()
            self.watchdog_stops += 1
        if self.left > 0 and self.right > 0:
            if self.blocked:
                self._stop()
                self.reflex_stops += 1
            else:
                self.position_cm += (self.left + self.right) / 2 / p.MAX_SPEED * FULL_SPEED_CM_S * dt
        if t >= self.next_telemetry:
            self.next_telemetry = t + TELEMETRY_S
            self.outbox.append(p.encode("T", self.distance_cm(), round(self.temp_c * 10),
                                        round(self.humidity * 10), int(self.moving), int(self.blocked)))

    def _stop(self) -> None:
        self.left = self.right = 0

    # --- serial input ---
    def receive(self, line: bytes) -> None:
        try:
            f = p.decode(line)
        except p.ProtocolError:
            return  # the firmware drops lines that fail the checksum
        self.last_msg = self.clock.now()
        if len(f) < 2 or not f[1].isdigit():
            return
        kind, seq, args = f[0], f[1], f[2:]
        try:
            ok = self._execute(kind, args)
        except ValueError:
            ok = "BAD"
        self.outbox.append(p.encode("K", seq) if ok is True else p.encode("E", seq, ok))

    def _execute(self, kind: str, args: List[str]):
        if kind == "D" and len(args) == 3:
            left, right, ms = (int(a) for a in args)
            if abs(left) > p.MAX_SPEED or abs(right) > p.MAX_SPEED or not 0 < ms <= p.MAX_DRIVE_MS:
                return "RANGE"
            self.left, self.right = left, right
            self.drive_until = self.clock.now() + ms / 1000
            return True
        if kind == "S" and not args:
            self._stop()
            return True
        if kind == "A" and len(args) == 1:
            level = int(args[0])
            if level not in (0, 1, 2):
                return "RANGE"
            self.alert_level = level
            self.beeps += level == 2
            return True
        if kind == "L" and len(args) == 2:
            row = int(args[0])
            if not 0 <= row < p.LCD_ROWS:
                return "RANGE"
            self.lcd[row] = args[1][:p.LCD_COLS]
            return True
        if kind == "P" and not args:
            return True
        return "BAD"


class SimLink:
    """Connects the Pi-side code to a SimArduino, like the UART would. Can drop lines."""

    def __init__(self, arduino: SimArduino, drop_sends: int = 0):
        self.arduino = arduino
        self.drop_sends = drop_sends
        self.sent: List[bytes] = []

    def send(self, line: bytes) -> None:
        self.sent.append(line)
        if self.drop_sends:
            self.drop_sends -= 1
            return
        self.arduino.receive(line)

    def readline(self) -> Optional[bytes]:
        return self.arduino.outbox.pop(0) if self.arduino.outbox else None
