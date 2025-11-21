"""
Main demo runner for local development (simulation).
Put sample images in test_images/ and run: python3 main.py
"""
from src.detector import Detector
from src.hardware_simulation import LED, Buzzer, LCD, MotorDriverSim
from src import utils
from src import logger as lg
import cv2
from pathlib import Path
import json
import sys

# CONFIG - update names if needed
MODELS = {
    "leaf": "models/leaf_best.pt",   # place your trained leaf model here
    "fruit": "models/fruit_best.pt"  # place your trained fruit model here
}
CLASS_NAMES = {
    "leaf": ["Early Blight","Healthy","Late Blight","Leaf Miner","Leaf Mold","Mosaic Virus","Septoria","Spider Mites","Yellow Leaf Curl Virus"],
    "fruit": ["Antracnose","Blossom_End_Rot","Catfaced","Fruit_Cracking","Healthy_Tomato","Late_Blight","Mold","Spotted_Wilt_Virus"]
}

def load_det_if_exists(key, path):
    p = Path(path)
    if p.exists():
        print(f"Loading {key} model from {path}")
        return Detector(str(p), class_names=CLASS_NAMES.get(key))
    else:
        print(f"{key} model not found at {path} — skipping")
        return None

def main_loop():
    # hardware sim
    led_r = LED("red"); led_y = LED("yellow"); led_g = LED("green")
    buzzer = Buzzer(); lcd = LCD(); motors = MotorDriverSim()

    # load models if present
    det_leaf = load_det_if_exists("leaf", MODELS["leaf"])
    det_fruit = load_det_if_exists("fruit", MODELS["fruit"])

    test_dir = Path("test_images")
    imgs = list(test_dir.glob("*.*"))
    if not imgs:
        print("No test images found in test_images/. Put sample images there and re-run.")
        return

    for img_path in imgs:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        print("Processing:", img_path.name)
        all_results = []
        if det_leaf:
            res = det_leaf.predict_image(img)
            for d in res:
                d["model"] = "leaf"
            all_results += res
        if det_fruit:
            res = det_fruit.predict_image(img)
            for d in res:
                d["model"] = "fruit"
            all_results += res

        # Annotate and save
        out_img_path = lg.save_annotated_image(img, all_results, out_name=img_path.stem + "_annot.jpg")

        # local alerts: if any detection confidence > 0.5 then alert
        alert = any(d["conf"] >= 0.5 for d in all_results)
        lcd.display(0, f"Image: {img_path.name}")
        lcd.display(1, f"Detections: {len(all_results)}")
        if alert:
            led_r.on()
            buzzer.beep(200)
            lcd.display(2, "ALERT: disease")
        else:
            led_g.on()
            lcd.display(2, "OK")
        # log
        record = {
            "ts": utils.timestamp(),
            "source_image": str(img_path),
            "annotated_image": str(out_img_path),
            "detections": all_results
        }
        lg.save_detection_log(record)
        # reset leds
        led_r.off(); led_g.off(); led_y.off()
    print("Done processing all test_images.")

if __name__ == "__main__":
    main_loop()

