import streamlit as st
import json
from pathlib import Path
import pandas as pd

from src.alerts import classify, is_healthy

LOG_DIR = Path("data") / "logs"
IMG_DIR = LOG_DIR / "images"

st.set_page_config(page_title="Tomato Robot Dashboard", layout="wide")
st.title("🍅 Tomato Robot - Dashboard")

# --- fetch logs ---
logs = sorted(LOG_DIR.glob("log_*.json"), reverse=True)

if not logs:
    st.info("No logs found. Run main.py first to generate logs (sample images in test_images/).")
else:
    # --- Sidebar filters ---
    st.sidebar.header("Filters")
    model_filter = st.sidebar.selectbox("Model", ["All", "Leaf", "Fruit"])
    status_filter = st.sidebar.selectbox("Health", ["All", "Healthy", "Diseased"])

    # --- Load logs into DataFrame for easy filtering ---
    records = [json.loads(f.read_text()) for f in logs[:50]]  # last 50 logs
    alerts = [r.get("alert") or classify(r.get("detections", [])).value for r in records]
    log_data = []
    for d in records:
        for det in d.get("detections", []):
            name = det.get("class_name") or "unknown"
            log_data.append({
                "timestamp": d.get("ts"),
                "image": d.get("source_image"),
                "annotated": d.get("annotated_image"),
                "class_name": name,
                "conf": det.get("conf"),
                "model": det.get("model"),
                "health": "Healthy" if is_healthy(name) else "Diseased"
            })

    # --- Alert summary, one per inspected image ---
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 Disease alerts", alerts.count("disease"))
    c2.metric("🟡 Check (possible disease)", alerts.count("watch"))
    c3.metric("🟢 Healthy / nothing found", alerts.count("ok"))

    if not log_data:
        st.warning("No detections in logs yet.")
    else:
        df = pd.DataFrame(log_data)

        # --- Apply filters ---
        if model_filter != "All":
            df = df[df["model"].fillna("").str.lower() == model_filter.lower()]
        if status_filter != "All":
            df = df[df["health"] == status_filter]

        st.subheader("Recent Detections")
        st.write(f"Showing {len(df)} detections from last {len(records)} logs")

        # --- Columns layout ---
        col1, col2 = st.columns([2,3])

        with col1:
            # Summary counts
            st.subheader("Detection Counts")
            counts = df["class_name"].value_counts()
            st.bar_chart(counts)

        with col2:
            st.subheader("Annotated Images")
            for idx, row in df.iterrows():
                st.markdown(f"**{row['timestamp']} | {row['image']} | {row['class_name']} {row['conf']:.0%} ({row['health']})**")
                if row["annotated"] and Path(row["annotated"]).exists():
                    st.image(str(row["annotated"]), width="stretch")
                st.markdown("---")
