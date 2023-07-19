import json
from time import sleep, time, ticks_ms

from machine import Pin, I2C

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

    
from uosc.server import split_oscstr, parse_message

from ht16k33segment import HT16K33Segment

import onewire 
import ds18x20

from rhb_pico_utils import run_server, toggle_startup_display, wifi_connection
import rhb_pico_utils


def manage_heater(temp: int):
    """Water heater and pump state machine"""
    try:
        if state["heater_status"] and temp >= TEMP_UPPER:
            state["cooling_down"] = True
            state["heater_status"] = 0
            heater_pin.off()
            pump_pin.off()
            rhb_pico_utils.display.set_blink_rate(0)
            print("Heater shutdown")
        elif not state["heater_status"] and temp < TEMP_LOWER:
            state["heater_status"] = ticks_ms()
            state["cooling_down"] = False
            rhb_pico_utils.display.set_blink_rate(2)
            pump_pin.on()
            sleep(2)
            heater_pin.on()
            print("Heater startup")
        elif not state["cooling_down"] and temp < TEMP_UPPER and (ticks_ms() - state["heater_status"]) > HEATER_RESET:
            state["heater_status"] = ticks_ms()
            pump_pin.on()
            heater_pin.off()
            sleep(2)
            heater_pin.on()
            print(f"Recycle heater at {temp}")
    except Exception as e:
        print(e)


def handle_osc(data, src, dispatch=None, strict=False):
    """Process any new OSC messages about pressure"""
    try:
        head, _ = split_oscstr(data, 0)
        if head.startswith('/'):
            messages = [(-1, parse_message(data, strict))]
        elif head == '#bundle':
            messages = parse_bundle(data, strict)
    except Exception as exc:
        if __debug__:
            print("Exception Data: %r", data)
        return

    try:
        for timetag, (oscaddr, tags, args) in messages:
            bcd = int(str(int(args[0])), 16)

            if "pressure" in oscaddr:
                rhb_pico_utils.display.set_number((bcd & 0xF0) >> 4, 0)
                rhb_pico_utils.display.set_number((bcd & 0x0F), 1)
            elif "temperature" in oscaddr and "cpu" not in oscaddr:
                if int(args[0]) > 100:
                    rhb_pico_utils.display.set_blink_rate(1)
                else:
                    rhb_pico_utils.display.set_blink_rate(0)
                rhb_pico_utils.display.set_number((bcd & 0xF0) >> 4, 2)
                rhb_pico_utils.display.set_number((bcd & 0x0F), 3)
                manage_heater(int(args[0]))
            rhb_pico_utils.display.draw()
            if __debug__:
                print(f"{time()} OSC message : {oscaddr} {tags} {args}")

            if dispatch:
                dispatch(timetag, (oscaddr, tags, args, src))
    except Exception as exc:
        print("Exception in OSC handler: %s", exc)


async def temp_loop():
    """Main temp processing loop"""
    while True:
        try:
            ds.convert_temp()
            for rom in roms:
                temp = int(float(ds.read_temp(rom)) * 9.0 / 5.0 + 32.0)
            print(f"Temperature: {temp}")
            manage_heater(temp)
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Exception in temp_loop: {e}")
            break
    rhb_pico_utils.reboot()


async def main_loop():
    """Main async loop"""
    try:
        print("Starting main loop...")
        temp_task = asyncio.create_task(temp_loop())
        server_task = asyncio.create_task(run_server(config["IP"], 8888, handle_osc))
        await temp_task
        await server_task
    except:
        rhb_pico_utils.reboot()


if __name__ == "__main__":
    rhb_pico_utils.led = Pin("LED", Pin.OUT)
    rhb_pico_utils.led.off()
    ow = onewire.OneWire(Pin(28, Pin.IN))
    ds = ds18x20.DS18X20(ow)
    roms = ds.scan()
    pump_pin = Pin(2, Pin.OUT)
    pump_pin.off()
    heater_pin = Pin(3, Pin.OUT)
    heater_pin.off()

    HEATER_RESET = 600000
    TEMP_UPPER = 75
    TEMP_LOWER = 70

    state = {
        "heater_status": 0,
        "cooling_down": False,
    }

    with open("config_home.json") as f:
        config = json.load(f)

    i2c = I2C(0, scl=Pin(17), sda=Pin(16))
    devices = i2c.scan()
    if devices:
        for d in devices:
            print(f"I2C device found: {hex(d)}")
    rhb_pico_utils.display = HT16K33Segment(i2c)
    rhb_pico_utils.display.set_brightness(15)
    
    try:
        toggle_startup_display(1)
        wlan = wifi_connection(config)
        sync_text = b"\x40\x40\x40\x40" # ----
        for i in range(len(sync_text)):
            rhb_pico_utils.display.set_glyph(sync_text[i], i)
        rhb_pico_utils.display.draw()
        asyncio.run(main_loop())
    except Exception as e:
        print(f"{e}")
        rhb_pico_utils.reboot()
    rhb_pico_utils.reboot()
    

    