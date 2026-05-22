import sys
from time import sleep

from gpiozero import PWMLED, Button, DigitalOutputDevice

# --- Hardware Configuration based on Final Pinout ---
# Pin 12 (GPIO 18) - Hardware PWM for LEDs
led_strip = PWMLED(18)

# Pin 18 (GPIO 24) - Standard Digital Out for Solenoid
lock_trigger = DigitalOutputDevice(24)

# Pin 16 (GPIO 23) - Digital In next to Pin 14 (GND)
# Pull-up is enabled internally by default in the Button class
lock_sensor = Button(23)


def clear_screen():
    # ANSI escape code om de terminal te wissen (Veilig, geen shell injectie risico)
    print("\033c", end="")


def get_sensor_text():
    # Returns status based on whether microswitch contacts are closed/connected
    if lock_sensor.is_pressed:
        return "🔒 CLOSED & SECURED"
    return "🔓 OPEN / RELEASED"


def run_interface():
    current_brightness = 0.0

    while True:
        clear_screen()
        print("=========================================")
        print("        HARDWARE TEST INTERFACE          ")
        print("=========================================")
        print(f" 1. Lock Sensor State : {get_sensor_text()}")
        print(f" 2. LED Strip Power   : {int(current_brightness * 100)}%")
        print("=========================================")
        print(" [O] - Open Lock Transiently (3 seconds)")
        print(" [L] - Set LED Brightness")
        print(" [R] - Refresh Status Screen")
        print(" [Q] - Quit Test Panel")
        print("=========================================")

        choice = input("Select an option: ").strip().lower()

        if choice == "o":
            print("\n⚡ Activating Solenoid Lock Module...")
            lock_trigger.on()

            # Brief pause to let physical mechanism move and update sensor state
            sleep(0.5)
            print(f" Live Sensor State: {get_sensor_text()}")

            print(" Holding open for 3 seconds...")
            sleep(2.5)

            print("🛑 Disengaging Solenoid...")
            lock_trigger.off()
            sleep(0.5)

        elif choice == "l":
            try:
                val = input("Enter brightness percentage (0 to 100): ").strip()
                pct = int(val)
                if 0 <= pct <= 100:
                    current_brightness = pct / 100.0
                    led_strip.value = current_brightness
                else:
                    print("⚠️ Please enter a number between 0 and 100.")
                    sleep(1.5)
            except ValueError:
                print("⚠️ Invalid number entry.")
                sleep(1.5)

        elif choice == "r":
            continue

        elif choice == "q":
            print("\nShutting down hardware outputs safely...")
            lock_trigger.off()
            led_strip.off()
            sys.exit()

        else:
            print("⚠️ Unknown option selected.")
            sleep(1.0)


if __name__ == "__main__":
    try:
        run_interface()
    except KeyboardInterrupt:
        print("\n\nExecution interrupted. Safely disabling all outputs.")
        lock_trigger.off()
        led_strip.off()
