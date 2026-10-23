"""
The Pi's client for the Arduino base: sends commands, waits for each acknowledgement,
retries lost lines, and keeps the latest telemetry.
"""
import time
from typing import Optional

from robot import protocol as p


class LinkTimeout(RuntimeError):
    """The Arduino did not acknowledge a command, even after retries."""


class CommandRejected(RuntimeError):
    pass


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class SerialLink:
    """The GPIO UART on the Pi (/dev/serial0). Not yet run on the robot."""

    def __init__(self, port: str = "/dev/serial0", baud: int = 115200):
        import serial  # pyserial, only needed on the robot
        self.port = serial.Serial(port, baud, timeout=0)
        self._buf = b""

    def send(self, line: bytes) -> None:
        self.port.write(line)

    def readline(self) -> Optional[bytes]:
        self._buf += self.port.read(256)
        if b"\n" not in self._buf:
            return None
        line, self._buf = self._buf.split(b"\n", 1)
        return line + b"\n"


class ArduinoBase:
    def __init__(self, link, clock=None, ack_timeout: float = 0.15, retries: int = 2):
        self.link = link
        self.clock = clock or SystemClock()
        self.ack_timeout = ack_timeout
        self.retries = retries
        self.telemetry = p.Telemetry()
        self.telemetry_at: Optional[float] = None
        self.bad_lines = 0
        self._seq = 0

    # --- commands ---
    def drive(self, left: int, right: int, ms: int) -> None:
        if abs(left) > p.MAX_SPEED or abs(right) > p.MAX_SPEED:
            raise ValueError(f"speed out of range: {left}, {right}")
        if not 0 < ms <= p.MAX_DRIVE_MS:
            raise ValueError(f"drive duration out of range: {ms} ms")
        self._command("D", left, right, ms)

    def stop(self) -> None:
        self._command("S")

    def alert(self, level: int) -> None:
        if level not in (0, 1, 2):
            raise ValueError(f"alert level out of range: {level}")
        self._command("A", level)

    def lcd(self, row: int, text: str) -> None:
        if not 0 <= row < p.LCD_ROWS:
            raise ValueError(f"LCD row out of range: {row}")
        self._command("L", row, p.lcd_text(text))

    def ping(self) -> None:
        self._command("P")

    def _command(self, kind: str, *args) -> None:
        # The same sequence number is reused on retries: every command is safe to repeat.
        self._seq = self._seq % 9999 + 1
        seq = str(self._seq)
        line = p.encode(kind, seq, *args)
        for _ in range(self.retries + 1):
            self.link.send(line)
            deadline = self.clock.now() + self.ack_timeout
            while self.clock.now() < deadline:
                f = self._read_one()
                if f is None:
                    self.clock.sleep(0.005)
                elif f and f[0] in "KE" and len(f) >= 2 and f[1] == seq:
                    if f[0] == "E":
                        raise CommandRejected(f"{kind} rejected: {f[2] if len(f) > 2 else '?'}")
                    return
        raise LinkTimeout(f"no acknowledgement for {line!r}")

    # --- input ---
    def poll(self) -> p.Telemetry:
        """Read everything waiting on the link; return the latest telemetry."""
        while self._read_one() is not None:
            pass
        return self.telemetry

    def _read_one(self):
        line = self.link.readline()
        if line is None:
            return None
        try:
            f = p.decode(line)
        except p.ProtocolError:
            self.bad_lines += 1
            return []
        if f and f[0] == "T":
            try:
                self.telemetry = p.Telemetry.from_fields(f)
                self.telemetry_at = self.clock.now()
            except p.ProtocolError:
                self.bad_lines += 1
        return f
