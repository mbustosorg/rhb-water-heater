import json
from machine import Pin, PWM, I2C
import ds18x20
from time import sleep, time, ticks_ms
import network
import uasyncio

try:
    import socket
except ImportError:
    import usocket as socket

try:
    import select
except ImportError:
    import uselect as select
    
try:
    import logging
except ImportError:
    import uosc.fakelogging as logging

from uosc.server import handle_osc
from uosc.server import split_oscstr, parse_message

from ht16k33segment import HT16K33Segment

import onewire 
import ds18x20


ow = onewire.OneWire(Pin(28, Pin.IN)) 
ds = ds18x20.DS18X20(ow)
roms = ds.scan()

led = Pin("LED", Pin.OUT)
led.off()
pump_pin = Pin(2, Pin.OUT)
pump_pin.off()
heater_pin = Pin(3, Pin.OUT)
heater_pin.off()

HEATER_RESET = 10000
TEMP_UPPER = 75
TEMP_LOWER = 70

state = {
    "heater_status": 0,
    "cooling_down": False,
}

log = logging.getLogger("uosc.minimal_server")

with open("config_home.json") as f:
    config = json.load(f)
    
MAX_DGRAM_SIZE = 1472

i2c = I2C(0, scl=Pin(17), sda=Pin(16))
devices = i2c.scan()
if devices:
    for d in devices:
        print(hex(d))

display = HT16K33Segment(i2c)
display.set_brightness(15)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)


def toggle_startup_display(count):
    if count % 6 == 0:
        sync_text = b"\x01\x01\x01\x01"
    elif count % 6 == 1:
        sync_text = b"\x02\x02\x02\x02"
    elif count % 6 == 2:
        sync_text = b"\x04\x04\x04\x04"
    elif count % 6 == 3:
        sync_text = b"\x08\x08\x08\x08"
    elif count % 6 == 4:
        sync_text = b"\x10\x10\x10\x10"
    elif count % 6 == 5:
        sync_text = b"\x20\x20\x20\x20"
    for i in range(len(sync_text)):
        display.set_glyph(sync_text[i], i)
    display.draw()


def manage_heater(temp: int):
    """Water heater and pump state machine"""
    try:
        if state["heater_status"] and temp >= TEMP_UPPER:
            state["cooling_down"] = True
            state["heater_status"] = 0
            heater_pin.off()
            pump_pin.off()
            display.set_blink_rate(0)
            log.info("Heater shutdown")
        elif not state["heater_status"] and temp < TEMP_LOWER:
            state["heater_status"] = ticks_ms()
            state["cooling_down"] = False
            display.set_blink_rate(2)
            pump_pin.on()
            sleep(2)
            heater_pin.on()
            log.info("Heater startup")
        elif not state["cooling_down"] and temp < TEMP_UPPER and (ticks_ms() - state["heater_status"]) > HEATER_RESET:
            state["heater_status"] = ticks_ms()
            pump_pin.on()
            heater_pin.off()
            sleep(2)
            heater_pin.on()
            log.info(f"Recycle heater at {temp}")
    except Exception as e:
        print(e)


def reboot():
    """Reset the machine""" 
    sleep(5)
    machine.reset()


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
            log.debug("Exception Data: %r", data)
        return

    try:
        for timetag, (oscaddr, tags, args) in messages:
            bcd = int(str(int(args[0])), 16)

            if "pressure" in oscaddr:
                display.set_number((bcd & 0xF0) >> 4, 0)
                display.set_number((bcd & 0x0F), 1)
            elif "temperature" in oscaddr and "cpu" not in oscaddr:
                if int(args[0]) > 100:
                    display.set_blink_rate(1)
                else:
                    display.set_blink_rate(0)
                display.set_number((bcd & 0xF0) >> 4, 2)
                display.set_number((bcd & 0x0F), 3)
                manage_heater(int(args[0]))
            display.draw()
            if __debug__:
                log.debug(f"{time()} OSC message : {oscaddr} {tags} {args}")

            if dispatch:
                dispatch(timetag, (oscaddr, tags, args, src))
    except Exception as exc:
        log.error("Exception in OSC handler: %s", exc)
        
        
def connect_to_wifi():
    """Connect to the wifi"""
    while True:
        wait = 2
        wlan.connect(config["WIFI_SSID"], config["WIFI_PASSWORD"])
        while wait < 12:
            status = wlan.status()
            if status >= 3:
                led.on()
                break
            toggle_startup_display(wait)
            wait += 1
            sleep(1)
        if wlan.status() != 3:
            print(f'network connection failed, retrying {wlan.status()}')
        else:
            print('connected')
            status = wlan.ifconfig()
            print('ip = ' + status[0] )
            break


async def run_server(saddr, port, handler=handle_osc):
    """Run the OSC Server asynchronously"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ai = socket.getaddrinfo(saddr, port)[0]
    sock.setblocking(False)
    sock.bind(ai[-1])
    p = select.poll()
    p.register(sock, select.POLLIN)
    poll = getattr(p, "ipoll", p.poll)

    log.info("Listening for OSC messages on %s:%i", saddr, port)
    while True:
        try:
            for res in poll(1):
                if res[1] & (select.POLLERR | select.POLLHUP):
                    log.debug("UDPServer.serve: unexpected socket error.")
                    break
                elif res[1] & select.POLLIN:
                    buf, addr = sock.recvfrom(MAX_DGRAM_SIZE)
                    handler(buf, addr)
            log.info(f"OSC tick {ticks_ms()}")    
            await uasyncio.sleep(1)
        except Exception as e:
            log.info(f"Exception in run_server: {e}")    
    sock.close()
    reboot()


async def loop():
    """Main temp processing loop"""
    while True:
        ds.convert_temp()
        for rom in roms:
            temp = int(float(ds.read_temp(rom)) * 9.0 / 5.0 + 32.0)
        log.info(f"{temp}")
        manage_heater(temp)
        await uasyncio.sleep(1)
            
            
async def main():
    """Main async loop"""
    try:
        print("Starting main loop...")
        main_task = uasyncio.create_task(loop())
        server_task = uasyncio.create_task(run_server(config["IP"], 8888))
        await main_task
        await server_task
    except:
        reboot()

try:
    toggle_startup_display(1)
    connect_to_wifi()
    sync_text = b"\x40\x40\x40\x40"
    for i in range(len(sync_text)):
        display.set_glyph(sync_text[i], i)
    display.draw()
    uasyncio.run(main())
except:
    reboot()
finally:
    reboot()
    

