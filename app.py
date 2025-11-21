import streamlit as st
import json
from pathlib import Path
from PIL import Image
import pandas as pd

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
    log_data = []
    for f in logs[:50]:  # last 50 logs
        d = json.loads(f.read_text())
        for det in d.get("detections", []):
            log_data.append({
                "timestamp": d.get("ts"),
                "image": d.get("source_image"),
                "annotated": d.get("annotated_image"),
                "class_name": det.get("class_name"),
                "conf": det.get("conf"),
                "model": det.get("model"),
                "health": "Healthy" if det.get("class_name").lower().find("healthy") >= 0 else "Diseased"
            })
    if not log_data:
        st.warning("No detections in logs yet.")
    else:
        df = pd.DataFrame(log_data)
        
        # --- Apply filters ---
        if model_filter != "All":
            df = df[df["model"].str.lower() == model_filter.lower()]
        if status_filter != "All":
            df = df[df["health"] == status_filter]

        st.subheader("Recent Detections")
        st.write(f"Showing {len(df)} detections from last {min(50,len(logs))} logs")
        
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
                st.markdown(f"**{row['timestamp']} | {row['image']} | {row['class_name']} ({row['health']})**")
                if row["annotated"] and Path(row["annotated"]).exists():
                    st.image(str(row["annotated"]), use_column_width=True)
                st.markdown("---")
