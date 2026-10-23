"""
Render a video of the robot patrolling a row: the real Pi code and the real models, with the
simulated Arduino standing in for the hardware. Every frame shows the camera view with
detections, the LEDs, buzzer and LCD as the firmware drives them, the telemetry, and a map
of the row.

  python tools/render_demo.py                     # docs/demo.mp4 and docs/demo.gif
  python tools/render_demo.py --stations 6 --no-obstacle
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from robot.base import ArduinoBase  # noqa: E402
from robot.patrol import Patrol, PatrolConfig  # noqa: E402
from robot.sim_arduino import FULL_SPEED_CM_S, FakeClock, SimArduino, SimLink  # noqa: E402
from run_robot import make_inspector  # noqa: E402
from src.alerts import is_healthy  # noqa: E402

W, H = 1280, 720
FPS = 10
BEEP_S = 0.3  # BEEP_MS in the firmware
CAM = (20, 80, 760, 500)          # x, y, w, h of the camera view
PANEL_X = 810
MAP_Y = 630

BG = (24, 24, 28)
FG = (235, 235, 235)
DIM = (130, 130, 130)
GREEN, YELLOW, RED = (80, 200, 80), (40, 210, 240), (60, 60, 230)
LCD_BG, LCD_FG = (70, 150, 90), (25, 45, 25)
FONT = cv2.FONT_HERSHEY_SIMPLEX
MONO = cv2.FONT_HERSHEY_PLAIN
ALERT_COLORS = {"ok": GREEN, "watch": YELLOW, "disease": RED}


class ListCamera:
    """Plays a fixed list of photos, as if the robot met these plants in this order."""

    def __init__(self, paths):
        self.paths = list(paths)
        self.i = 0
        self.last_path = None

    def capture(self):
        self.last_path = self.paths[self.i % len(self.paths)]
        self.i += 1
        return cv2.imread(str(self.last_path))


# Chosen to show each alert level and two known failures: fruit1 is a false alarm (the leaf
# model reads "Early Blight" on a fruit) and fruit10 is a miss (visible mold, reported OK).
# This is a demonstration order, not an evaluation.
SHOWCASE = ["leaf16", "leaf1", "fruit10", "leaf13", "fruit1", "leaf17", "leaf5", "fruit12"]


def alternate_leaf_and_fruit(folder: Path):
    leaves = sorted(folder.glob("leaf*.jpg"), key=lambda p: int("".join(filter(str.isdigit, p.stem))))
    fruits = sorted(folder.glob("fruit*.jpg"), key=lambda p: int("".join(filter(str.isdigit, p.stem))))
    out = []
    for pair in zip(leaves, fruits):
        out.extend(pair)
    return out


def text(img, s, x, y, scale=0.6, color=FG, thick=1, font=FONT):
    cv2.putText(img, s, (x, y), font, scale, color, thick, cv2.LINE_AA)


def label(img, s, x, y, scale=0.9, color=FG, thick=2):
    (tw, th), base = cv2.getTextSize(s, FONT, scale, thick)
    cv2.rectangle(img, (x - 8, y - th - 10), (x + tw + 8, y + base + 4), (0, 0, 0), -1)
    text(img, s, x, y, scale, color, thick)


def fit(image, w, h):
    ih, iw = image.shape[:2]
    s = min(w / iw, h / ih)
    resized = cv2.resize(image, (int(iw * s), int(ih * s)))
    canvas = np.zeros((h, w, 3), np.uint8)
    y0, x0 = (h - resized.shape[0]) // 2, (w - resized.shape[1]) // 2
    canvas[y0:y0 + resized.shape[0], x0:x0 + resized.shape[1]] = resized
    return canvas, s, x0, y0


class Renderer:
    """Attached to the simulated clock: draws a frame every 1/FPS seconds of robot time."""

    def __init__(self, arduino: SimArduino, camera: ListCamera, stations: int, cfg: PatrolConfig,
                 obstacle_cm, clear_after_s):
        self.ard = arduino
        self.camera = camera
        self.cfg = cfg
        self.frames = []
        self.next_frame = 0.0
        self.view = None            # annotated camera image of the last inspection
        self.last_record = None
        self.plants = []            # (position_cm, alert)
        self.beeps_seen = 0
        self.beep_until = -1.0
        self.reflex_at = None
        self.clear_after_s = clear_after_s
        self.cleared_at = None
        self.obstacle_cm = obstacle_cm
        segment_cm = cfg.speed / 255 * FULL_SPEED_CM_S * cfg.segment_ms / 1000
        self.row_cm = max(stations * segment_cm * 1.1, (obstacle_cm or 0) + 30)

    # --- clock device ---
    def tick(self, t, dt):
        if self.ard.reflex_stops and self.reflex_at is None:
            self.reflex_at = t
        if (self.clear_after_s is not None and self.reflex_at is not None and self.cleared_at is None
                and t - self.reflex_at >= self.clear_after_s):
            self.ard.obstacle_cm = None
            self.cleared_at = t
        if self.ard.beeps > self.beeps_seen:
            self.beeps_seen = self.ard.beeps
            self.beep_until = t + BEEP_S
        if t >= self.next_frame:
            self.next_frame += 1 / FPS
            self.frames.append(self.draw(t))

    # --- patrol callback ---
    def on_station(self, record):
        self.last_record = record
        self.plants.append((self.ard.position_cm, record["alert"]))
        image = cv2.imread(str(self.camera.last_path))
        self.view = self.annotate(image, record["detections"])
        t = self.ard.clock.now()
        if record["alert"] == "disease":
            self.beep_until = t + BEEP_S
        for _ in range(int(FPS * 1.5)):  # hold the result on screen
            self.frames.append(self.draw(t, inspecting=True))

    def annotate(self, image, detections):
        view, s, x0, y0 = fit(image, CAM[2], CAM[3])
        for d in detections:
            x1, y1, x2, y2 = (int(v * s) for v in d["bbox"])
            color = GREEN if is_healthy(d["class_name"]) else RED
            cv2.rectangle(view, (x0 + x1, y0 + y1), (x0 + x2, y0 + y2), color, 2)
            label = f"{d['class_name']} {d['conf']:.0%} ({d['model']})"
            (tw, th), _ = cv2.getTextSize(label, FONT, 0.5, 1)
            ly = max(y0 + y1, th + 6)
            cv2.rectangle(view, (x0 + x1, ly - th - 6), (x0 + x1 + tw + 6, ly), color, -1)
            text(view, label, x0 + x1 + 3, ly - 4, 0.5, (0, 0, 0))
        return view

    # --- drawing ---
    def state(self, inspecting):
        if inspecting:
            return "INSPECTING", FG
        if self.ard.moving:
            return "DRIVING", GREEN
        if self.ard.blocked:
            return "OBSTACLE: waiting", YELLOW
        return "STOPPED, settling", DIM

    def draw(self, t, inspecting=False):
        img = np.full((H, W, 3), BG, np.uint8)
        text(img, "AsaaseTom Guard", 20, 45, 1.1, FG, 2)
        text(img, "robot patrol  |  real models and Pi code, simulated Arduino", 330, 44, 0.6, DIM)
        text(img, f"t = {t:5.1f} s", W - 150, 44, 0.6, DIM)

        # camera view
        x, y, w, h = CAM
        if self.view is not None:
            view = self.view if inspecting else (self.view * 0.35).astype(np.uint8)
            img[y:y + h, x:x + w] = view
        cv2.rectangle(img, (x, y), (x + w, y + h), (70, 70, 70), 1)
        state, color = self.state(inspecting)
        label(img, state, x + 18, y + 38, 0.9, color)
        if inspecting and self.last_record:
            r = self.last_record
            label(img, f"Plant {r['station']}: {r['alert'].upper()}", x + 18, y + h - 18, 0.9,
                  ALERT_COLORS[r["alert"]])
            text(img, Path(str(self.camera.last_path)).name, x + w - 130, y + h - 16, 0.5, DIM)

        # LCD
        px = PANEL_X
        text(img, "LCD (20x4)", px, 100, 0.55, DIM)
        cv2.rectangle(img, (px, 110), (px + 440, 250), LCD_BG, -1)
        for row, line in enumerate(self.ard.lcd):
            text(img, line, px + 14, 145 + row * 30, 1.6, LCD_FG, 2, MONO)

        # LEDs and buzzer
        text(img, "LEDs", px, 290, 0.55, DIM)
        for i, (name, col, level) in enumerate((("green", GREEN, 0), ("yellow", YELLOW, 1), ("red", RED, 2))):
            on = self.ard.alert_level == level
            cx = px + 30 + i * 90
            cv2.circle(img, (cx, 325), 22, col if on else (55, 55, 55), -1)
            if on:
                cv2.circle(img, (cx, 325), 28, col, 2)
            text(img, name, cx - 22, 370, 0.5, FG if on else DIM)
        beeping = t <= self.beep_until
        cv2.rectangle(img, (px + 290, 303), (px + 440, 347), RED if beeping else (55, 55, 55), -1)
        text(img, "BUZZER", px + 318, 332, 0.6, FG if beeping else DIM, 2 if beeping else 1)

        # telemetry
        text(img, "Telemetry (Arduino, 5 Hz)", px, 410, 0.55, DIM)
        d = self.ard.distance_cm()
        rows = [
            ("ultrasonic", f"{d} cm" if d >= 0 else "clear"),
            ("temperature", f"{self.ard.temp_c:.1f} C"),
            ("humidity", f"{self.ard.humidity:.0f} %"),
            ("wheels L / R", f"{self.ard.left} / {self.ard.right}"),
            ("travelled", f"{self.ard.position_cm:.0f} cm"),
        ]
        for i, (k, v) in enumerate(rows):
            text(img, k, px, 445 + i * 30, 0.6, DIM)
            text(img, v, px + 200, 445 + i * 30, 0.65, FG)
        if self.cleared_at is not None and t - self.cleared_at < 2.5:
            text(img, "obstacle removed", px, 600, 0.65, GREEN, 2)

        # row map
        x0, x1 = 40, W - 40
        scale = (x1 - x0) / self.row_cm
        cv2.line(img, (x0, MAP_Y + 40), (x1, MAP_Y + 40), (90, 90, 90), 2)
        text(img, "row", x0, MAP_Y + 70, 0.5, DIM)
        for pos, alert in self.plants:
            px_ = int(x0 + pos * scale)
            cv2.line(img, (px_, MAP_Y + 24), (px_, MAP_Y + 40), (90, 90, 90), 1)
            cv2.circle(img, (px_, MAP_Y + 14), 9, ALERT_COLORS[alert], -1)
        if self.ard.obstacle_cm is not None:
            ox = int(x0 + self.ard.obstacle_cm * scale)
            cv2.rectangle(img, (ox, MAP_Y + 15), (ox + 22, MAP_Y + 65), (150, 150, 150), -1)
            text(img, "obstacle", ox - 20, MAP_Y + 10, 0.5, DIM)
        rx = int(x0 + self.ard.position_cm * scale)
        cv2.rectangle(img, (rx - 18, MAP_Y + 28), (rx + 18, MAP_Y + 52), (200, 160, 60), -1)
        text(img, "robot", rx - 20, MAP_Y + 85, 0.5, FG)
        return img


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stations", type=int, default=8)
    ap.add_argument("--obstacle-cm", type=float, default=95.0)
    ap.add_argument("--no-obstacle", action="store_true")
    ap.add_argument("--clear-after", type=float, default=3.0,
                    help="seconds after the reflex stop before the obstacle is taken away")
    ap.add_argument("--order", choices=["showcase", "alternate"], default="showcase",
                    help="showcase: photos chosen to show each alert level; alternate: leaf, fruit, leaf, ...")
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo"))
    args = ap.parse_args(argv)
    obstacle = None if args.no_obstacle else args.obstacle_cm

    clock = FakeClock()
    arduino = SimArduino(clock, obstacle_cm=obstacle)
    base = ArduinoBase(SimLink(arduino), clock=clock)
    folder = ROOT / "test_images"
    photos = ([folder / f"{name}.jpg" for name in SHOWCASE] if args.order == "showcase"
              else alternate_leaf_and_fruit(folder))
    camera = ListCamera(photos)
    cfg = PatrolConfig(stations=args.stations)
    renderer = Renderer(arduino, camera, args.stations, cfg, obstacle,
                        None if obstacle is None else args.clear_after)
    clock.devices.append(renderer)

    inspect = make_inspector(["fruit", "leaf"], 0.25, 0.5)
    result = Patrol(base, camera, inspect, cfg, on_station=renderer.on_station).run()
    for _ in range(FPS * 2):
        renderer.frames.append(renderer.draw(clock.now()))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out.with_suffix(".mp4")), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for f in renderer.frames:
        writer.write(f)
    writer.release()

    from PIL import Image
    gif = [Image.fromarray(cv2.cvtColor(cv2.resize(f, (800, 450), interpolation=cv2.INTER_AREA),
                                        cv2.COLOR_BGR2RGB)).quantize(colors=128)
           for f in renderer.frames[::2]]
    gif[0].save(out.with_suffix(".gif"), save_all=True, append_images=gif[1:], duration=1000 * 2 // FPS,
                loop=0, optimize=True)
    print(f"{result.end_reason}: {result.stations} plants {result.alerts}, obstacle stops "
          f"{result.obstacle_stops}; {len(renderer.frames)} frames, {len(renderer.frames) / FPS:.0f} s")
    print(f"wrote {out.with_suffix('.mp4')} and {out.with_suffix('.gif')}")


if __name__ == "__main__":
    main()
