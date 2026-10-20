#define PIN_INT_1PPS 4
#define PIN_INT_25K 23
#define PIN_OUTPUT_SEQ 13 // RFOUT1
#define PIN_OUTPUT_0_1Hz_A 27 // RFOUT2
#define PIN_OUTPUT_0_1Hz_B 25 // GOUT3
#define PIN_OUTPUT_0_1Hz_C 14 //GOUT5
#include <Arduino.h>
#include "sequence.h"
#include <esp32/rom/ets_sys.h>

const uint32_t OUTPUT_PINS_MASK = (1 << 13) | (1 << 27) | (1 << 25) | (1 << 14);

volatile unsigned long counter = 0;
volatile bool triggered = false;
volatile bool shouldOutput = false;
volatile bool shouldTrigger = false;

int sequenceLength = 2014;
volatile int sequencePoint;
volatile uint32_t sequenceValue;

void IRAM_ATTR ISR_1PPS() {
  if (shouldOutput) {
    GPIO.out |= (1 << 27) | (1 << 25) | (1 << 14);
    ets_delay_us(10);
    GPIO.out &= ~((1 << 27) | (1 << 25) | (1 << 14));
    if (shouldTrigger) {
      sequenceValue = 0;
      sequencePoint = -1;
      shouldTrigger = false;
    }
    shouldOutput = false;
  }

  triggered = true;
}

void IRAM_ATTR ISR_25K() {
  if (sequenceValue > 0) sequenceValue--;
  else {
    sequencePoint++;
    if (sequencePoint > sequenceLength) sequencePoint--;
    else {
      uint32_t v = sequence[sequencePoint];
      sequenceValue = v * 25 - 1;
      GPIO.out |= (1 << PIN_OUTPUT_SEQ);
      ets_delay_us(10);
      GPIO.out &= ~(1 << PIN_OUTPUT_SEQ);
    }
  }
}

void setup() {
  Serial.begin(115200);
  sequencePoint = sequenceLength;
  sequenceValue = 0;

  pinMode(PIN_OUTPUT_SEQ, OUTPUT);
  pinMode(PIN_OUTPUT_0_1Hz_A, OUTPUT);
  pinMode(PIN_OUTPUT_0_1Hz_B, OUTPUT);
  pinMode(PIN_OUTPUT_0_1Hz_C, OUTPUT);
  digitalWrite(PIN_OUTPUT_SEQ, LOW);
  digitalWrite(PIN_OUTPUT_0_1Hz_A, LOW);
  digitalWrite(PIN_OUTPUT_0_1Hz_B, LOW);
  digitalWrite(PIN_OUTPUT_0_1Hz_C, LOW);
  attachInterrupt(digitalPinToInterrupt(PIN_INT_1PPS), ISR_1PPS, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_INT_25K), ISR_25K, RISING);
}

void loop() {
  if (triggered) {
    counter += 1;
    if (counter % 10 == 9) shouldOutput = true;
    Serial.println(counter % 10 == 0 ? "T+" : "T");
    delay(5);
    triggered = false;
  }
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() >= 1) {
      if (input[0] == 'D') {
        int value = input.substring(1).toInt();
        counter += value;
      } else if (input[0] == 'E') {
        int value = input.substring(1).toInt();
        if (value == 1) {
          shouldTrigger = true;
        } else {
          shouldTrigger = false;
          sequencePoint = sequenceLength;
          sequenceValue = 0;
        }
      } else if (input[0] == 'S') {
        int length = (Serial.read() << 8) + Serial.read();
        Serial.println("Setting sequence length to " + String(length));
      }
    }
  }  
}
