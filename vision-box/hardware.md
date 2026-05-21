# Hardware Wiring Documentation

## 📌 System Architecture Overview

This access control node uses a Raspberry Pi 4 to manage an electronic entry point. It controls a high-power dual-MOSFET drive board (XY-MOS) to switch external power for a solenoid lock, drives a second XY-MOS board for an LED light strip, and monitors a physical latch status sensor (microswitch)

## 🔌 Complete Pinout Matrix

| Target Component | Component Pin Name | Raspberry Pi 4 Pin Name | Physical Pin Number | Function |
| --- | --- | --- | --- | --- |
| LED Strip Module | TRIG / PWM | GPIO 18 | Pin 12 | Hardware PWM0 Clock (2 kHz anti-flicker) |
| LED Strip Module | GND | GND | Pin 09 | Common Control Ground Reference |
| Lock Module | TRIG | GPIO 24 | Pin 18 | Digital Output (Binary Lock/Unlock) |
| Lock Module | GND | GND | Pin 20 | Common Control Ground Reference |
| Microswitch Sensor | Terminal 1 | GND | Pin 14 | Ground Reference Line |
| Microswitch Sensor | Terminal 2 | GPIO 23 | Pin 16 | Digital Input (Internal 3.3V Pull-Up) |

## 🛠️ Step-by-Step Wiring Maps## 1. Solenoid Lock Control Loop

The solenoid lock is an inductive load and requires a parallel 1N4007 flyback diode to block high-voltage spikes from destroying the MOSFETs [1209893].

* Control Side:
* Connect Pi Pin 18 (GPIO 24) to the Lock XY-MOS board TRIG terminal.
  * Connect Pi Pin 20 (GND) or common ground to the Lock XY-MOS board GND input terminal.
* Power Input Side:
* Connect the Positive (+) wire of your external 12V/24V power supply to the XY-MOS VIN+ terminal.
  * Connect the Negative (-) wire of your external 12V/24V power supply to the XY-MOS VIN- terminal.
* Load Output Side (With Inductive Protection):
* Connect the Solenoid Lock wires directly into the XY-MOS OUT+ and OUT- terminals.
  * Clamp the 1N4007 Diode directly into those same output screw terminals in parallel with the lock:
  * Silver Stripe Side (Cathode): Insert into the OUT+ terminal.
    * Solid Black Side (Anode): Insert into the OUT- terminal.
  * Safety Note: If the wire distance between the board and the lock exceeds 30 cm, solder this diode directly across the lock's terminal leads instead of at the board to eliminate cable-broadcasted electromagnetic interference (EMI).

## 2. LED Strip Control Loop

* Control Side:
* Connect Pi Pin 12 (GPIO 18) to the LED XY-MOS board TRIG terminal.
  * Connect Pi Pin 09 (GND) to the LED XY-MOS board GND input terminal.
* Power & Load Side:
* Connect the external LED power supply (12V/24V) to VIN+ and VIN-.
  * Connect the LED strip leads directly to OUT+ and OUT-. No flyback diode is required for resistive LED loads.

## 3. Latch Monitoring Microswitch

This switch tracks physical door state. It uses the Pi's internal pull-up resistor to pull the line to 3.3V when open, grounding it to 0V when closed.

* Connect one terminal of the microswitch to Pi Pin 14 (GND).
* Connect the adjacent terminal of the microswitch to Pi Pin 16 (GPIO 23).

## ⚠️ Critical Fail-Safe Checklist

   1. Diode Orientation: Ensure the silver stripe on the flyback diode faces the positive output terminal (OUT+). Installing it backwards will create an immediate short circuit that will destroy your component traces.
   2. Avoid Boot-Console Pins: Never connect a lock or high-power driver to GPIO 14 or GPIO 15. These pins output a live high signal during the Raspberry Pi boot sequence, causing your lock to unexpectedly pop open whenever the system resets.
   3. Common Grounding: Ensure all grounds (GND) trace back to a unified electrical reference point to prevent floating voltages from throwing off your sensor readings.

If you are ready to configure the system to run automatically on boot, let me know if you would like a clean Systemd Service Unit template file to handle automatic software launches.
