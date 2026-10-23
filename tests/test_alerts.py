from src.alerts import AlertLevel, classify, is_healthy, top_disease


def det(name, conf):
    return {"class_name": name, "conf": conf, "bbox": [0, 0, 1, 1]}


def test_no_detections_is_ok():
    assert classify([]) is AlertLevel.OK


def test_confident_healthy_leaf_does_not_alert():
    # the original bug: any detection at 0.5 or more raised the disease alarm
    assert classify([det("Healthy", 0.97)]) is AlertLevel.OK
    assert classify([det("Healthy_Tomato", 0.9)]) is AlertLevel.OK


def test_confident_disease_alerts():
    assert classify([det("Late Blight", 0.81)]) is AlertLevel.DISEASE


def test_disease_at_exactly_the_threshold_alerts():
    assert classify([det("Septoria", 0.5)], alert_threshold=0.5) is AlertLevel.DISEASE


def test_weak_disease_is_a_watch_not_an_alarm():
    assert classify([det("Leaf Mold", 0.3)]) is AlertLevel.WATCH


def test_disease_wins_over_healthy_in_the_same_image():
    assert classify([det("Healthy", 0.95), det("Early Blight", 0.6)]) is AlertLevel.DISEASE


def test_threshold_is_configurable():
    assert classify([det("Mold", 0.6)], alert_threshold=0.7) is AlertLevel.WATCH


def test_is_healthy_handles_missing_names():
    assert not is_healthy(None)
    assert not is_healthy("")
    assert is_healthy("healthy")


def test_top_disease_ignores_healthy():
    worst = top_disease([det("Healthy", 0.99), det("Mold", 0.4), det("Late_Blight", 0.7)])
    assert worst["class_name"] == "Late_Blight"
    assert top_disease([det("Healthy", 0.99)]) is None
