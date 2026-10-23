"""
Main demo runner for local development (simulation).
Put sample images in test_images/ and run: python3 main.py
Options: --models leaf fruit, --images DIR, --conf 0.25, --alert-threshold 0.5
"""
from src.detector import Detector
from src.hardware_simulation import LED, Buzzer, LCD, MotorDriverSim
from src.alerts import AlertLevel, classify, top_disease
from src import utils
from src import logger as lg
import argparse
import cv2
from pathlib import Path

MODELS = {
    "leaf": "models/leaf_best.pt",
    "fruit": "models/fruit_best.pt"
}

def load_det_if_exists(key, path, conf):
    p = Path(path)
    if p.exists():
        print(f"Loading {key} model from {path}")
        return Detector(str(p), conf=conf)
    else:
        print(f"{key} model not found at {path}, skipping")
        return None

def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="AsaaseTom Guard: tomato disease detection (simulation mode)")
    ap.add_argument("--models", nargs="+", choices=sorted(MODELS), default=sorted(MODELS),
                    help="which detectors to run on each image (default: both)")
    ap.add_argument("--images", default="test_images", help="folder of images to process")
    ap.add_argument("--conf", type=float, default=0.25, help="minimum confidence for a detection")
    ap.add_argument("--alert-threshold", type=float, default=0.5,
                    help="disease confidence that raises the full alert (red LED and buzzer)")
    return ap.parse_args(argv)

def main_loop(argv=None):
    args = parse_args(argv)

    # hardware sim
    led_r = LED("red"); led_y = LED("yellow"); led_g = LED("green")
    buzzer = Buzzer(); lcd = LCD(); motors = MotorDriverSim()

    detectors = {k: load_det_if_exists(k, MODELS[k], args.conf) for k in args.models}
    detectors = {k: d for k, d in detectors.items() if d}
    if not detectors:
        print("No models found in models/. Nothing to run.")
        return

    imgs = sorted(p for p in Path(args.images).glob("*.*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not imgs:
        print(f"No images found in {args.images}/. Put sample images there and re-run.")
        return

    counts = {level: 0 for level in AlertLevel}
    for img_path in imgs:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        print("Processing:", img_path.name)
        motors.stop()  # the robot pauses while it inspects a plant
        all_results = []
        for key, det in detectors.items():
            res = det.predict_image(img)
            for d in res:
                d["model"] = key
            all_results += res

        out_img_path = lg.save_annotated_image(img, all_results, out_name=img_path.stem + "_annot.jpg")

        # local alerts: green = healthy or nothing found, yellow = possible disease, red + buzzer = disease
        level = classify(all_results, alert_threshold=args.alert_threshold)
        counts[level] += 1
        worst = top_disease(all_results)
        led_r.off(); led_y.off(); led_g.off()
        lcd.clear()
        lcd.display(0, f"Image: {img_path.name}")
        lcd.display(1, f"Detections: {len(all_results)}")
        if level is AlertLevel.DISEASE:
            led_r.on()
            buzzer.beep(200)
            lcd.display(2, "ALERT: disease")
            lcd.display(3, f"{worst['class_name']} {worst['conf']:.0%}")
        elif level is AlertLevel.WATCH:
            led_y.on()
            lcd.display(2, "CHECK: possible disease")
            lcd.display(3, f"{worst['class_name']} {worst['conf']:.0%}")
        else:
            led_g.on()
            lcd.display(2, "OK: healthy")

        lg.save_detection_log({
            "ts": utils.timestamp(),
            "source_image": str(img_path),
            "annotated_image": str(out_img_path),
            "alert": level.value,
            "detections": all_results
        })
    led_r.off(); led_y.off(); led_g.off()
    print("Done. " + ", ".join(f"{lvl.value}: {n}" for lvl, n in counts.items()))
    return counts

if __name__ == "__main__":
    main_loop()
