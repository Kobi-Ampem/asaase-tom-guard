"""
Run the robot's patrol along a row.

  python run_robot.py --sim                     # simulated Arduino, photos from test_images/
  python run_robot.py --sim --obstacle-cm 150   # put an obstacle 1.5 m down the row
  python run_robot.py --port /dev/serial0       # on the robot
"""
import argparse
import sys

from robot.base import ArduinoBase
from robot.patrol import Patrol, PatrolConfig
from src import logger as lg
from src import utils
from src.alerts import classify


def make_inspector(models, conf, alert_threshold):
    from src.detector import Detector
    detectors = {k: Detector(f"models/{k}_best.pt", conf=conf) for k in models}

    def inspect(image):
        dets = []
        for key, det in detectors.items():
            for d in det.predict_image(image):
                d["model"] = key
                dets.append(d)
        return classify(dets, alert_threshold=alert_threshold), dets
    return inspect


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--sim", action="store_true", help="simulated Arduino and folder camera")
    where.add_argument("--port", help="UART to the Arduino, e.g. /dev/serial0")
    ap.add_argument("--images", default="test_images", help="photos for the simulated camera")
    ap.add_argument("--obstacle-cm", type=float, help="simulation: obstacle this far down the row")
    ap.add_argument("--stations", type=int, default=10)
    ap.add_argument("--models", nargs="+", choices=["fruit", "leaf"], default=["fruit", "leaf"])
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--alert-threshold", type=float, default=0.5)
    args = ap.parse_args(argv)

    if args.sim:
        from robot.camera import FolderCamera
        from robot.sim_arduino import FakeClock, SimArduino, SimLink
        clock = FakeClock()
        base = ArduinoBase(SimLink(SimArduino(clock, obstacle_cm=args.obstacle_cm)), clock=clock)
        camera = FolderCamera(args.images)
    else:
        from robot.base import SerialLink
        from robot.camera import PiCamera
        base = ArduinoBase(SerialLink(args.port))
        camera = PiCamera()

    def log_station(record):
        image_name = camera.last_path.stem if camera.last_path else f"station{record['station']}"
        print(f"plant {record['station']:>2}: {record['alert'].upper():<7} "
              + ", ".join(f"{d['class_name']} {d['conf']:.0%}" for d in record["detections"]))
        lg.save_detection_log({"ts": utils.timestamp(), "source_image": image_name, **record})

    inspect = make_inspector(args.models, args.conf, args.alert_threshold)
    cfg = PatrolConfig(stations=args.stations)
    result = Patrol(base, camera, inspect, cfg, on_station=log_station).run()
    print(f"Patrol {result.end_reason}: {result.stations} plants, alerts {result.alerts}, "
          f"obstacle stops {result.obstacle_stops}")
    return 0 if result.end_reason == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
