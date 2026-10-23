import pytest

from robot import protocol as p


def test_round_trip():
    line = p.encode("D", 7, 150, -150, 1200)
    assert line.startswith(b"$D,7,150,-150,1200*") and line.endswith(b"\n")
    assert p.decode(line) == ["D", "7", "150", "-150", "1200"]


def test_checksum_matches_the_nmea_rule():
    # XOR of "P,1": 'P' ^ ',' ^ '1' = 0x50 ^ 0x2C ^ 0x31 = 0x4D
    assert p.encode("P", 1) == b"$P,1*4D\n"


def test_a_flipped_byte_is_rejected():
    line = bytearray(p.encode("D", 1, 100, 100, 500))
    line[6] = ord("9")  # 100 becomes 900 on the wire
    with pytest.raises(p.ProtocolError, match="checksum"):
        p.decode(bytes(line))


@pytest.mark.parametrize("bad", [b"D,1*00\n", b"$D,1\n", b"$D*1*00\n", b"\xff\xfe\n", b"\n"])
def test_malformed_lines_are_rejected(bad):
    with pytest.raises(p.ProtocolError):
        p.decode(bad)


def test_reserved_characters_cannot_be_sent():
    with pytest.raises(p.ProtocolError):
        p.encode("L", 1, 0, "a*b")


def test_lcd_text_is_made_safe_and_fits():
    assert p.lcd_text("Late Blight, 81%") == "Late Blight  81%"
    assert p.lcd_text("é$*x") == "   x"
    assert len(p.lcd_text("x" * 50)) == p.LCD_COLS


def test_telemetry_parses_and_scales():
    t = p.Telemetry.from_fields(["T", "57", "295", "710", "1", "0"])
    assert (t.dist_cm, t.temp_c, t.humidity, t.moving, t.blocked) == (57, 29.5, 71.0, True, False)


def test_telemetry_marks_a_failed_dht_read():
    t = p.Telemetry.from_fields(["T", "-1", str(p.NO_READING), str(p.NO_READING), "0", "0"])
    assert t.temp_c is None and t.humidity is None and t.dist_cm == -1


def test_bad_telemetry_is_rejected():
    with pytest.raises(p.ProtocolError):
        p.Telemetry.from_fields(["T", "x", "1", "1", "0", "0"])
