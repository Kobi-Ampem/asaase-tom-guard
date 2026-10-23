# AsaaseTom Guard: tomato disease detection robot

**1st place, JHS category, RAIL Phase II Robotics Cohort II Challenge, KNUST, January 2026**
([KNUST news](https://www.knust.edu.gh/index.php/news/news-items/st-louis-shs-opoku-ware-ma-jhs-win-rail-phase-ii-robotics-challenge),
[GES Kumasi Metro](https://web.facebook.com/GesKumasiMetro/posts/opoku-ware-ma-jhs-robotics-team-wins-with-smart-crop-disease-detection-systemthe/1474798337981988/)).
Built in 2025 with the Opoku Ware M/A JHS robotics team, which I trained and mentored.

A robot that drives along tomato rows, photographs leaves and fruit, detects disease
with two YOLOv8 models and warns the farmer on the spot with LEDs, a buzzer and an LCD,
while every inspection is logged to a dashboard.

## How it works

```
camera image ──> leaf detector (9 classes) ──┐
             └─> fruit detector (8 classes) ─┴─> alert level ──> LEDs, buzzer, LCD
                                                      └─────────> JSON log + annotated image ──> Streamlit dashboard
```

| Alert | When | Robot output |
|---|---|---|
| 🟢 OK | nothing found, or only healthy plants | green LED |
| 🟡 CHECK | a disease below the alert threshold (default 0.5) | yellow LED, disease name on the LCD |
| 🔴 DISEASE | a disease at or above the alert threshold | red LED, buzzer, disease name on the LCD |

On the robot, this pipeline ran on a Raspberry Pi with a camera, on a four-wheel-drive
chassis, with an Arduino handling the sensors and the outputs, motor drivers included.
That on-robot code is not in this repository: here the LEDs, buzzer, LCD and motors
are simulated (`src/hardware_simulation.py`), so the whole pipeline runs on a laptop.

## Models

Two YOLOv8n detectors, fine-tuned from the COCO-pretrained `yolov8n.pt` for 30 epochs
at 640 px on a Colab GPU (Ultralytics 8.3.229). Figures are on each dataset's
validation split, read from the checkpoints' training records.

| Model | Classes | mAP50 | mAP50-95 | Precision | Recall |
|---|---|---|---|---|---|
| Leaf (`models/leaf_best.pt`) | 9: Early Blight, Late Blight, Leaf Miner, Leaf Mold, Mosaic Virus, Septoria, Spider Mites, Yellow Leaf Curl Virus, Healthy | 0.931 | 0.829 | 0.873 | 0.881 |
| Fruit (`models/fruit_best.pt`) | 8: Anthracnose, Blossom End Rot, Catfaced, Fruit Cracking, Late Blight, Mold, Spotted Wilt Virus, Healthy | 0.760 | 0.419 | 0.791 | 0.718 |

Datasets (both CC BY 4.0, Roboflow Universe):
[tomato leaf diseases](https://universe.roboflow.com/kampem/tomato-leaf-diseases-4xa5i-5cg52/dataset/1) and
[tomato fruit diseases](https://universe.roboflow.com/tomato-fruit-diseases/tomato-fruit-diseases-detection/dataset/3).

## Run it

```bash
pip install -r requirements.txt
python main.py                       # both detectors on test_images/
python main.py --models leaf         # leaf detector only
python main.py --alert-threshold 0.6 # stricter alarm
streamlit run app.py                 # dashboard over data/logs/
```

## Tests

```bash
pip install pytest
pytest            # alert logic, simulated hardware and logging; plus the model tests when ultralytics is installed
```

CI runs the fast tests on every push.

## Limitations

- Metrics are validation-split figures; there is no separate held-out test run yet.
- The fruit model finds diseased regions better than it outlines them (mAP50 0.76 against mAP50-95 0.42).
- Both detectors run on every image, because the pipeline cannot yet tell a leaf photo from a fruit photo,
  and the leaf model misfires on fruit: on the 43 test images it fired on 14 of the 19 fruit photos
  (once "Early Blight" at 91%) and changed the alert on 4 of them. The fruit model fired on 4 of the 24 leaf
  photos without changing any alert. Suppressing overlapping boxes across the two models halved the
  wrong-model boxes but changed no alerts, so it was not adopted. Use `--models` when you know which one
  you are looking at; the real fix is a leaf-or-fruit decision before detection.
