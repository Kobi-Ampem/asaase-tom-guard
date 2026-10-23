"""
The Pi-side robot code against the simulated Arduino: link, safety rules and patrol.
"""
import pytest

from robot import protocol as p
from robot.base import ArduinoBase, CommandRejected, LinkTimeout
from robot.patrol import Patrol, PatrolConfig
from robot.sim_arduino import STOP_CM, WATCHDOG_S, FakeClock, SimArduino, SimLink
from src.alerts import AlertLevel


def make(obstacle_cm=None, drop_sends=0):
    clock = FakeClock()
    arduino = SimArduino(clock, obstacle_cm=obstacle_cm)
    base = ArduinoBase(SimLink(arduino, drop_sends=drop_sends), clock=clock)
    return clock, arduino, base


# --- link ---

def test_drive_is_acknowledged_and_stops_by_itself():
    clock, ard, base = make()
    base.drive(150, 150, 500)
    assert (ard.left, ard.right) == (150, 150)
    clock.sleep(0.6)
    assert not ard.moving


def test_a_lost_command_is_retried():
    clock, ard, base = make(drop_sends=1)
    base.alert(2)
    assert ard.alert_level == 2 and ard.beeps == 1
    assert len(base.link.sent) == 2


def test_a_dead_link_raises_after_retries():
    clock, ard, base = make(drop_sends=10)
    with pytest.raises(LinkTimeout):
        base.stop()
    assert len(base.link.sent) == base.retries + 1


def test_out_of_range_values_are_refused_on_both_sides():
    clock, ard, base = make()
    with pytest.raises(ValueError):
        base.drive(300, 0, 100)
    # if a bad value did reach the Arduino, it would refuse it too
    ard.receive(p.encode("D", 5, 300, 0, 100))
    assert p.decode(ard.outbox[-1]) == ["E", "5", "RANGE"]
    base.link.send(p.encode("A", 6, 9))
    with pytest.raises(CommandRejected):
        base._command("A", 9)


def test_corrupted_lines_from_the_arduino_are_counted_not_trusted():
    clock, ard, base = make()
    ard.outbox.append(b"$T,5,0,0,1,1*00\n")
    t = base.poll()
    assert base.bad_lines == 1 and not t.blocked


def test_lcd_text_reaches_the_display():
    clock, ard, base = make()
    base.lcd(1, "Late Blight, 81%")
    assert ard.lcd[1] == "Late Blight  81%"


def test_telemetry_arrives():
    clock, ard, base = make(obstacle_cm=120)
    clock.sleep(0.3)
    t = base.poll()
    assert t.dist_cm == 120 and t.temp_c == 29.5 and base.telemetry_at is not None


# --- safety rules in the firmware ---

def test_watchdog_stops_the_robot_when_the_pi_goes_quiet():
    clock, ard, base = make()
    base.drive(150, 150, 5000)
    clock.sleep(WATCHDOG_S + 0.1)
    assert not ard.moving and ard.watchdog_stops == 1


def test_obstacle_reflex_stops_forward_motion_without_the_pi():
    clock, ard, base = make(obstacle_cm=STOP_CM + 10)
    base.drive(255, 255, 3000)
    clock.sleep(0.9)
    assert not ard.moving and ard.reflex_stops >= 1
    assert ard.distance_cm() < STOP_CM


def test_reversing_away_from_an_obstacle_is_allowed():
    clock, ard, base = make(obstacle_cm=10)
    base.drive(-150, -150, 500)
    clock.sleep(0.2)
    assert ard.moving


# --- patrol ---

class StubCamera:
    last_path = None

    def capture(self):
        return "image"


def inspector(levels):
    it = iter(levels)

    def inspect(image):
        level = next(it)
        dets = [] if level is AlertLevel.OK else [{"class_name": "Late Blight", "conf": 0.8}]
        return level, dets
    return inspect


def test_patrol_inspects_every_station_and_alerts():
    clock, ard, base = make()
    levels = [AlertLevel.OK, AlertLevel.DISEASE, AlertLevel.WATCH]
    result = Patrol(base, StubCamera(), inspector(levels), PatrolConfig(stations=3)).run()
    assert result.end_reason == "done" and result.stations == 3
    assert result.alerts == {"ok": 1, "watch": 1, "disease": 1}
    assert ard.beeps == 1 and ard.alert_level == 1
    assert ard.watchdog_stops == 0  # the heartbeat kept the link alive through every segment
    assert ard.position_cm > 0 and not ard.moving


def test_patrol_gives_up_on_a_permanent_obstacle():
    clock, ard, base = make(obstacle_cm=40)
    cfg = PatrolConfig(stations=10, max_retries=2)
    result = Patrol(base, StubCamera(), inspector([AlertLevel.OK] * 10), cfg).run()
    assert result.end_reason == "blocked"
    assert result.obstacle_stops == cfg.max_retries + 1
    assert ard.distance_cm() >= 0 and not ard.moving


def test_patrol_resumes_when_the_obstacle_moves_away():
    clock, ard, base = make(obstacle_cm=40)

    class ClearAfter:
        def tick(self, t, dt):
            if t > 3.0:
                ard.obstacle_cm = None
    clock.devices.append(ClearAfter())

    class LcdWatcher:
        stale = False

        def tick(self, t, dt):
            # driving again while the LCD still says "waiting" would mislead the farmer
            if ard.moving and ard.lcd[2].startswith("Obstacle"):
                LcdWatcher.stale = True
    clock.devices.append(LcdWatcher())
    result = Patrol(base, StubCamera(), inspector([AlertLevel.OK] * 4), PatrolConfig(stations=4)).run()
    assert result.end_reason == "done" and result.stations == 4 and result.obstacle_stops >= 1
    assert not LcdWatcher.stale


def test_a_failed_capture_is_logged_not_fatal():
    clock, ard, base = make()

    class Broken:
        last_path = None

        def capture(self):
            return None
    result = Patrol(base, Broken(), inspector([]), PatrolConfig(stations=2)).run()
    assert result.stations == 2 and all(not r["camera_ok"] for r in result.log)
