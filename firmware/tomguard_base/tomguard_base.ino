// AsaaseTom Guard: Arduino base firmware.
// Rebuilt in October 2026 after the competition (the original was not kept); not yet run on the robot.
//
// Arduino Uno + L293D motor shield (Adafruit Motor Shield v1 compatible, AFMotor library), four DC
// motors, HC-SR04 ultrasonic, DHT22, red/yellow/green LEDs, active buzzer, 20x4 I2C LCD.
// The Raspberry Pi sends commands over the hardware UART (D0/D1) using the protocol described in
// robot/protocol.py. robot/sim_arduino.py is a Python twin of this file: keep the rules in step.
//
// Safety rules that hold even if the Pi hangs:
//   - every drive command stops by itself after its duration;
//   - watchdog: no valid message for WATCHDOG_MS while moving -> stop;
//   - obstacle reflex: ultrasonic under STOP_CM while driving forward -> stop.

#include <AFMotor.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "DHT.h"

// --- rules (same values as robot/sim_arduino.py and robot/protocol.py) ---
const unsigned long WATCHDOG_MS = 1000;
const int STOP_CM = 20;
const unsigned long TELEMETRY_MS = 200;
const int MAX_SPEED = 255;
const long MAX_DRIVE_MS = 5000;
const int MAX_RANGE_CM = 400;
const int NO_READING = -999;
const int LCD_ROWS = 4;
const int LCD_COLS = 20;

// --- timing of the sensors ---
const unsigned long SONAR_MS = 60;     // HC-SR04 needs ~60 ms between pings
const unsigned long DHT_MS = 2000;     // DHT22 gives a new reading every 2 s at most
const unsigned long BEEP_MS = 300;

// --- pins left free by the motor shield (it uses D3-D8, D11, D12) ---
const int DHT_PIN = 2;
const int BUZZER_PIN = 9;   // active buzzer: tone() would take Timer2, which drives motor PWM on D3 and D11
const int LED_GREEN = 13;
const int TRIG_PIN = A0;
const int ECHO_PIN = A1;
const int LED_RED = A2;
const int LED_YELLOW = A3;
// A4/A5 are the I2C bus for the LCD

AF_DCMotor frontLeft(1), rearLeft(2), rearRight(3), frontRight(4);
LiquidCrystal_I2C lcd(0x27, LCD_COLS, LCD_ROWS);
DHT dht(DHT_PIN, DHT22);

int leftSpeed = 0, rightSpeed = 0;
unsigned long driveUntil = 0, lastMsg = 0;
unsigned long lastSonar = 0, lastDht = 0, lastTelemetry = 0, beepUntil = 0;
bool beeping = false;
int distanceCm = -1;
int tempX10 = NO_READING, humX10 = NO_READING;

char rx[64];
byte rxLen = 0;
bool rxOverflow = false;

// ---------- motors ----------

void setMotor(AF_DCMotor &m, int speed) {
  m.setSpeed(abs(speed));
  m.run(speed > 0 ? FORWARD : speed < 0 ? BACKWARD : RELEASE);
}

void setWheels(int left, int right) {
  leftSpeed = left;
  rightSpeed = right;
  setMotor(frontLeft, left);
  setMotor(rearLeft, left);
  setMotor(frontRight, right);
  setMotor(rearRight, right);
}

void stopWheels() { setWheels(0, 0); }

bool moving() { return leftSpeed != 0 || rightSpeed != 0; }

// ---------- sensors ----------

int readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long us = pulseIn(ECHO_PIN, HIGH, 25000UL);  // ~4 m round trip; blocks 25 ms at most
  if (us == 0) return -1;
  int cm = us / 58;
  return cm <= MAX_RANGE_CM ? cm : -1;
}

void readDht() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  tempX10 = isnan(t) ? NO_READING : (int)round(t * 10);
  humX10 = isnan(h) ? NO_READING : (int)round(h * 10);
}

bool blocked() { return distanceCm >= 0 && distanceCm < STOP_CM; }

// ---------- outputs ----------

void setAlert(int level) {
  digitalWrite(LED_GREEN, level == 0);
  digitalWrite(LED_YELLOW, level == 1);
  digitalWrite(LED_RED, level == 2);
  if (level == 2) {
    digitalWrite(BUZZER_PIN, HIGH);
    beeping = true;
    beepUntil = millis() + BEEP_MS;
  }
}

void lcdRow(int row, const char *text) {
  char line[LCD_COLS + 1];
  snprintf(line, sizeof(line), "%-20s", text);  // pad so old text is overwritten
  lcd.setCursor(0, row);
  lcd.print(line);
}

// ---------- protocol ----------

byte xorOf(const char *s) {
  byte cs = 0;
  while (*s) cs ^= *s++;
  return cs;
}

void sendBody(const char *body) {
  char cs[3];
  snprintf(cs, sizeof(cs), "%02X", xorOf(body));
  Serial.print('$');
  Serial.print(body);
  Serial.print('*');
  Serial.print(cs);
  Serial.print('\n');
}

void reply(const char *seq, const char *error) {
  char body[24];
  if (error) snprintf(body, sizeof(body), "E,%s,%s", seq, error);
  else snprintf(body, sizeof(body), "K,%s", seq);
  sendBody(body);
}

void sendTelemetry() {
  char body[48];
  snprintf(body, sizeof(body), "T,%d,%d,%d,%d,%d", distanceCm, tempX10, humX10, moving(), blocked());
  sendBody(body);
}

bool toLong(const char *s, long &out) {
  if (!*s) return false;
  char *end;
  out = strtol(s, &end, 10);
  return *end == '\0';
}

bool allDigits(const char *s) {
  if (!*s) return false;
  for (; *s; s++) if (!isdigit(*s)) return false;
  return true;
}

// Returns NULL on success or the error code to send back.
const char *execute(const char *kind, char **args, int n) {
  long a, b, c;
  if (!strcmp(kind, "D") && n == 3) {
    if (!toLong(args[0], a) || !toLong(args[1], b) || !toLong(args[2], c)) return "BAD";
    if (abs(a) > MAX_SPEED || abs(b) > MAX_SPEED || c <= 0 || c > MAX_DRIVE_MS) return "RANGE";
    setWheels(a, b);
    driveUntil = millis() + c;
    return NULL;
  }
  if (!strcmp(kind, "S") && n == 0) {
    stopWheels();
    return NULL;
  }
  if (!strcmp(kind, "A") && n == 1) {
    if (!toLong(args[0], a)) return "BAD";
    if (a < 0 || a > 2) return "RANGE";
    setAlert(a);
    return NULL;
  }
  if (!strcmp(kind, "L") && n == 2) {
    if (!toLong(args[0], a)) return "BAD";
    if (a < 0 || a >= LCD_ROWS) return "RANGE";
    lcdRow(a, args[1]);
    return NULL;
  }
  if (!strcmp(kind, "P") && n == 0) return NULL;
  return "BAD";
}

void handleLine(char *line) {
  // $BODY*CS  -- drop anything that fails the checksum
  if (line[0] != '$') return;
  char *star = strchr(line, '*');
  if (!star || strchr(star + 1, '*') || strlen(star + 1) != 2) return;
  *star = '\0';
  char *body = line + 1;
  char cs[3];
  snprintf(cs, sizeof(cs), "%02X", xorOf(body));
  if (strcasecmp(cs, star + 1) != 0) return;
  lastMsg = millis();

  char *fields[6];
  int n = 0;
  fields[n++] = body;
  for (char *p = body; *p && n < 6; p++) {
    if (*p == ',') {
      *p = '\0';
      fields[n++] = p + 1;
    }
  }
  if (n < 2 || !allDigits(fields[1])) return;
  reply(fields[1], execute(fields[0], fields + 2, n - 2));
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (!rxOverflow) {
        rx[rxLen] = '\0';
        handleLine(rx);
      }
      rxLen = 0;
      rxOverflow = false;
    } else if (c != '\r') {
      if (rxLen < sizeof(rx) - 1) rx[rxLen++] = c;
      else rxOverflow = true;  // drop the whole over-long line
    }
  }
}

// ---------- main ----------

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  dht.begin();
  lcd.init();
  lcd.backlight();
  stopWheels();
  setAlert(0);
  lcdRow(0, "AsaaseTom Guard");
  lcdRow(1, "Waiting for Pi");
}

void loop() {
  readSerial();
  unsigned long now = millis();

  // the rules use subtraction so they survive millis() wrapping after ~49 days
  if (moving() && (long)(now - driveUntil) >= 0) stopWheels();
  if (moving() && now - lastMsg > WATCHDOG_MS) stopWheels();

  if (now - lastSonar >= SONAR_MS) {
    lastSonar = now;
    distanceCm = readDistanceCm();
  }
  if (blocked() && leftSpeed > 0 && rightSpeed > 0) stopWheels();

  if (now - lastDht >= DHT_MS) {
    lastDht = now;
    readDht();
  }
  if (beeping && (long)(now - beepUntil) >= 0) {
    digitalWrite(BUZZER_PIN, LOW);
    beeping = false;
  }
  if (now - lastTelemetry >= TELEMETRY_MS) {
    lastTelemetry = now;
    sendTelemetry();
  }
}
