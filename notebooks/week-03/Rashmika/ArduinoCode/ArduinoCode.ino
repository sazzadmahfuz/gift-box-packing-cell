
#define PUL_PIN      3
#define DIR_PIN      4
#define INPUT_A_PIN  5
#define ENA_PIN      6

const int STEP_DELAY = 500;
const unsigned long DEBOUNCE_TIME = 50;

int lastSensorReading = HIGH;
int stableSensorState = HIGH;

unsigned long lastChangeTime = 0;

void setup() {
  pinMode(ENA_PIN, OUTPUT);
  pinMode(PUL_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(INPUT_A_PIN, INPUT_PULLUP);

  digitalWrite(ENA_PIN, LOW);
  digitalWrite(PUL_PIN, HIGH);
  digitalWrite(DIR_PIN, LOW);
}

void loop() {

  // Read proximity sensor
  int sensorReading = digitalRead(INPUT_A_PIN);

  // Detect input change
  if (sensorReading != lastSensorReading) {
    lastChangeTime = millis();
    lastSensorReading = sensorReading;
  }

  // Accept input only after it remains stable
  if (millis() - lastChangeTime >= DEBOUNCE_TIME) {
    stableSensorState = sensorReading;
  }

  // Control ENA using filtered sensor signal
  if (stableSensorState == HIGH) {
    digitalWrite(ENA_PIN, HIGH);  // Enable motor
  }
  else {
    digitalWrite(ENA_PIN, LOW);   // Disable motor
  }

  // Continuous pulse generation (never stopped by sensor)
  digitalWrite(PUL_PIN, LOW);
  delayMicroseconds(STEP_DELAY);

  digitalWrite(PUL_PIN, HIGH);
  delayMicroseconds(STEP_DELAY);
}
