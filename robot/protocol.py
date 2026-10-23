"""
Wire protocol between the Raspberry Pi and the Arduino, over the GPIO UART (115200 baud).

Every message is one ASCII line, NMEA style:   $BODY*CS\\n
BODY is comma-separated fields and CS is the XOR of BODY's bytes as two hex digits,
so a line corrupted on the wire fails the check and is dropped instead of acted on.

Pi -> Arduino (each carries a sequence number the Arduino echoes back):
  D,<seq>,<left>,<right>,<ms>   drive; speeds -255..255; stops by itself after ms (max 5000)
  S,<seq>                       stop now
  A,<seq>,<level>               alert: 0 ok (green), 1 check (yellow), 2 disease (red and buzzer)
  L,<seq>,<row>,<text>          write LCD row 0-3, up to 20 characters
  P,<seq>                       ping

Arduino -> Pi:
  K,<seq>                       command accepted
  E,<seq>,<code>                command rejected: BAD (malformed) or RANGE (value out of range)
  T,<dist_cm>,<temp_x10>,<hum_x10>,<moving>,<blocked>
                                telemetry at 5 Hz; dist_cm is -1 with no echo and the
                                DHT22 fields are -999 when the sensor read fails
"""
from dataclasses import dataclass
from typing import List

MAX_SPEED = 255
MAX_DRIVE_MS = 5000
LCD_ROWS = 4
LCD_COLS = 20
NO_READING = -999


class ProtocolError(ValueError):
    pass


def checksum(body: str) -> str:
    cs = 0
    for ch in body.encode("ascii"):
        cs ^= ch
    return f"{cs:02X}"


def encode(*fields) -> bytes:
    body = ",".join(str(f) for f in fields)
    if any(c in body for c in "$*\n\r"):
        raise ProtocolError(f"reserved character in {body!r}")
    return f"${body}*{checksum(body)}\n".encode("ascii")


def decode(line: bytes) -> List[str]:
    """Return the fields of a valid line, or raise ProtocolError."""
    try:
        text = line.decode("ascii").strip()
    except UnicodeDecodeError as e:
        raise ProtocolError("not ASCII") from e
    if not text.startswith("$") or text.count("*") != 1:
        raise ProtocolError(f"malformed line {text!r}")
    body, cs = text[1:].split("*")
    if checksum(body) != cs.upper():
        raise ProtocolError(f"checksum mismatch in {text!r}")
    return body.split(",")


def lcd_text(text: str) -> str:
    """Make text safe for an L message: printable ASCII, no field separators, fits the row."""
    clean = "".join(c if 32 <= ord(c) < 127 and c not in ",$*" else " " for c in text)
    return clean[:LCD_COLS]


@dataclass
class Telemetry:
    dist_cm: int = -1
    temp_c: float = None
    humidity: float = None
    moving: bool = False
    blocked: bool = False

    @classmethod
    def from_fields(cls, fields: List[str]) -> "Telemetry":
        if len(fields) != 6 or fields[0] != "T":
            raise ProtocolError(f"not a telemetry message: {fields}")
        try:
            dist, temp, hum, moving, blocked = (int(f) for f in fields[1:])
        except ValueError as e:
            raise ProtocolError(f"bad telemetry values: {fields}") from e
        return cls(
            dist_cm=dist,
            temp_c=None if temp == NO_READING else temp / 10,
            humidity=None if hum == NO_READING else hum / 10,
            moving=bool(moving),
            blocked=bool(blocked),
        )
