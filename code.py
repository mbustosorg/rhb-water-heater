"""
 Copyright (C) 2024 Mauricio Bustos (m@bustos.org)
 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.
"""

import json
import time
import supervisor
import asyncio
import traceback

import board
import busio
import digitalio
import analogio

from adafruit_ht16k33 import segments
import adafruit_onewire.bus
import adafruit_ds18x20

import microosc
import rhb_utils

def manage_heater(temp):
    try:
        if state["safety_shutdown"]:
            heater_pin.value = False
            pump_pin.value = False
            safety_shutdown_pin.value = True
            return
        if state["heater_status"] and temp >= TEMP_UPPER:
            state["cooling_down"] = True
            state["heater_status"] = 0
            heater_pin.value = False
            pump_pin.value = False
            if rhb_utils.display:
                rhb_utils.display.blink_rate = 0
            print("Heater shutdown")
        elif not state["heater_status"] and temp <= TEMP_LOWER:
            state["heater_status"] = supervisor.ticks_ms()
            state["cooling_down"] = False
            state["temp_at_heater_start"] = temp
            if rhb_utils.display:
                rhb_utils.display.blink_rate = 2
            pump_pin.value = True
            time.sleep(2)
            heater_pin.value = True
            print("Heater startup")
        elif (not state["cooling_down"] and temp < TEMP_UPPER
              and (supervisor.ticks_ms() - state["heater_status"]) > HEATER_RESET):
            if temp <= state["temp_at_heater_start"] - 1:
                state["safety_shutdown"] = True
                return
            state["heater_status"] = supervisor.ticks_ms()
            pump_pin.value = True
            heater_pin.value = False
            time.sleep(2)
            heater_pin.value = True
            print(f"Recycle heater at {temp}")
    except Exception as e:
        print(e)


def propane_pressure_handler(msg):
    """Accumulator pressure, owned by rhb-sensor-monitor.  Receive only.

    microosc dispatches on msg.addr.startswith(key), so this is also handed
    /pressure_fine -- the unrounded value on the same prefix.  Match exactly;
    these two digits show the rounded one.
    """
    if msg.addr != "/pressure":
        return
    # Say so once per connection.  Silence here is ambiguous otherwise: a
    # display that never changes looks the same whether the monitor has gone
    # quiet or the read path has stopped dispatching.
    if not _pressure_seen[0]:
        _pressure_seen[0] = True
        print(f"Receiving /pressure, first value {msg.args[0]}")
    rhb_utils.set_two_digits(msg.args[0], 0, 1)


def read_water_pressure():
    adc_raw = pressure_adc.value
    sensor_voltage = (adc_raw / 65535) * 3.3
    return max(0.0, (sensor_voltage - 0.5) / 4.0 * 100.0)


def shutdown_heater(reason):
    """Drop the heater and pump.  Safe to call from any state."""
    if state["heater_status"] or pump_pin.value or heater_pin.value:
        print(f"Heater off: {reason}")
    state["heater_status"] = 0
    state["cooling_down"] = False
    heater_pin.value = False
    pump_pin.value = False
    if rhb_utils.display:
        rhb_utils.display.blink_rate = 0


def scan_probes():
    """Enumerate the bath probes and put them in 9 bit mode.

    The reading is used as whole degrees F, so 12 bit resolution -- the
    library default -- resolves 0.0625C that is thrown away by the int().
    It costs 750ms of conversion per read against 94ms at 9 bit (0.5C), and
    that conversion is a tight poll of a bit-banged bus with the event loop
    blocked behind it.  Eight times less exposure for no visible loss.

    The setting lives in the scratchpad, not EEPROM, so it has to be applied
    every time the probe is enumerated.
    """
    try:
        found = [adafruit_ds18x20.DS18X20(ow, d) for d in ow.scan()]
    except Exception as exception:
        print("OneWire scan failed:", exception)
        return []
    for sensor in found:
        try:
            sensor.resolution = 9
        except Exception as exception:
            print("Could not set probe resolution:", exception)
    print(f"OneWire probes: {len(found)}")
    return found


def read_and_display_temp():
    """Read the bath probe and display it.  None when there is no reading.

    A probe that is missing or unreadable must never come back as 0F.  That
    is below TEMP_LOWER, so manage_heater would light the heater on a
    temperature nobody measured, and the recycle check compares against
    temp_at_heater_start -- also 0 -- so the safety shutdown never fires and
    it reheats every HEATER_RESET forever.  No reading means heater off.
    """
    global ds_sensors
    if not ds_sensors:
        # The probe can miss the boot-time scan.  Look again rather than run
        # blind until somebody power-cycles the board.
        ds_sensors = scan_probes()
    temp = None
    for sensor in ds_sensors:
        try:
            reading = int(sensor.temperature * 9.0 / 5.0 + 32.0)
        except Exception as e:
            print("Probe read failed:", e)
            continue
        if TEMP_PLAUSIBLE_LOW <= reading <= TEMP_PLAUSIBLE_HIGH:
            temp = reading
        else:
            print(f"Implausible probe reading {reading}F ignored")
    if temp is None:
        print("Temperature: no reading")
        shutdown_heater("no usable temperature reading")
        if rhb_utils.display:
            for i in (2, 3):
                rhb_utils.display.set_digit_raw(i, 0x40)  # --, no reading
        return None
    print(f"Temperature: {temp}")
    manage_heater(temp)
    if rhb_utils.display:
        rhb_utils.display[2] = str((temp // 10) % 10)
        rhb_utils.display[3] = str(temp % 10)
    return temp


def client_endpoints(spec):
    """Parse a MOBILE_CLIENTS spec into (host, port) pairs.

    Entries are "host" for the usual OSC port, or "host:port" for listeners
    that are somewhere else -- the body display, for one, listens on 10002.
    """
    endpoints = []
    for entry in spec.split(","):
        entry = entry.strip()
        if not entry:
            continue
        host, _, port = entry.partition(":")
        endpoints.append((host.strip(), int(port) if port else OSC_PORT))
    return endpoints


def send_to_all(msgs):
    """Send every message to every listener, backing off from dead ones.

    Several listeners are phones that are absent most of the time.  Each send
    to an absent host costs SEND_TIMEOUT with the event loop stopped, so a
    host that fails is dropped for the rest of the cycle and then skipped for
    a growing number of cycles.  That matters for more than cadence: while
    this is blocking, osc_loop is not polling, and inbound /pressure is
    sitting in a 2K socket buffer waiting to be overrun.
    """
    if not osc_client:
        return
    for host, port in mobile_endpoints:
        key = (host, port)
        if _skip_cycles.get(key, 0) > 0:
            _skip_cycles[key] -= 1
            continue
        osc_client.host = host
        osc_client.port = port
        failed = None
        for msg in msgs:
            try:
                osc_client.send(msg)
            except Exception as e:
                failed = e
                break  # it will not answer for the rest of them either
        if failed is None:
            _fail_counts[key] = 0
        else:
            n = _fail_counts.get(key, 0) + 1
            _fail_counts[key] = n
            _skip_cycles[key] = min(2 ** n, MAX_SKIP_CYCLES)
            print(f"Send to {host}:{port} failed ({failed}); skipping {_skip_cycles[key]}")


async def connect_network():
    """One bounded connection attempt.  Brings up OSC when it succeeds.

    Awaits rather than blocks, so a down link no longer holds up temp_loop.
    The `async' matters beyond style: MicroPython accepts `await' inside a
    plain `def' and quietly compiles it into a generator, and awaiting that
    fails with "'generator' object has no attribute '__await__'".
    """
    global pool, osc_server, osc_client, mobile_endpoints
    deadline = time.monotonic() + CONNECT_TIMEOUT
    count = 0
    # The waiting lives here, not in rhb_utils -- see ethernet_connection.
    while True:
        pool = rhb_utils.ethernet_connection(config["IP"])
        if pool:
            break
        if time.monotonic() >= deadline:
            print(f"Ethernet link down after {CONNECT_TIMEOUT}s")
            return False
        rhb_utils.toggle_connecting_display(count)
        count += 1
        await asyncio.sleep(0.5)
    osc_server = microosc.OSCServer(pool, config["IP"], OSC_PORT, dispatch_map)
    # microosc hardcodes a 1ms timeout on the receive socket.  Every
    # _available() and read_udp() is an SPI transaction to the W5500, so a
    # real read cannot finish inside 1ms: it consumes the bytes and then
    # raises ETIMEDOUT, which poll() swallows as "no data".  The packets
    # arrive, drain out of the chip, and are never dispatched.
    osc_server._sock.settimeout(RX_TIMEOUT)
    # microosc sizes its receive buffer at 128 bytes.  A datagram longer than
    # that can only be read in part, and the leftover desynchronises every
    # read after it.
    osc_server._buf = bytearray(RX_BUFFER)
    mobile_endpoints = client_endpoints(config["MOBILE_CLIENTS"])
    # One socket for every listener.  microosc.OSCClient holds a socket for its
    # lifetime and the W5500 only has eight of them, so a client per listener
    # runs the chip out.  sendto() takes the destination per call, so the host
    # and port are just swapped before each send.
    # Bound every write so an absent listener cannot stall the loop; set on
    # the pool default so the client socket picks it up, after the server
    # socket above has already been made with the blocking default.
    pool.setdefaulttimeout(SEND_TIMEOUT)
    osc_client = (
        microosc.OSCClient(pool, mobile_endpoints[0][0], mobile_endpoints[0][1])
        if mobile_endpoints
        else None
    )
    pool.setdefaulttimeout(None)
    _pressure_seen[0] = False
    if rhb_utils.display:
        for i in range(2):
            rhb_utils.display.set_digit_raw(i, 0x40)  # -- until /pressure arrives
    return True


async def network_loop():
    while True:
        if not pool:
            if not await connect_network():
                # temp_loop keeps reading and displaying on its own 5s tick
                if rhb_utils.display:
                    for i in range(2):
                        rhb_utils.display.set_digit_raw(i, 0x40)  # no pressure yet
                await asyncio.sleep(CONNECT_RETRY)
                continue
        await asyncio.sleep(1)


def poll_osc():
    """Read exactly one datagram and dispatch it.  Never raises.

    Not osc_server.poll(), and not recvfrom_into either.  Both keep calling
    read_udp until they have as many bytes as were asked for, and read_udp
    parses an 8 byte UDP header on every call -- so once a read stops part
    way through a datagram, the next one reads payload as a header and the
    stream is desynchronised.  microosc's read_string() then finds no null
    terminator and raises ValueError, which poll() does not catch: it escapes
    osc_loop and reboots the board.

    read_udp takes the length from the datagram's own header, so asking it
    for the whole buffer returns one datagram and stops on the boundary.
    """
    sock = osc_server._sock
    try:
        if sock._available() <= 0:
            return
        length, data = sock._interface.read_udp(sock._socknum, len(osc_server._buf))
    except Exception as exception:
        print("OSC read failed:", exception)
        return
    if not length:
        return
    osc_server._buf[:length] = data
    try:
        message = microosc.parse_osc_packet(osc_server._buf, length)
    except Exception as exception:
        # The header parse has drifted off a datagram boundary and read
        # payload as a length.  Throw away what is queued so the next read
        # starts clean rather than compounding the error.
        print(f"Discarding {length} byte OSC packet: {exception}")
        for _ in range(8):
            try:
                if sock._available() <= 0:
                    break
                sock._interface.read_udp(sock._socknum, len(osc_server._buf))
            except Exception:
                break
        return
    try:
        osc_server._dispatch(message)
    except Exception as exception:
        print(f"Handler for {message.addr} failed: {exception}")


async def osc_loop():
    while True:
        if osc_server:
            poll_osc()
        await asyncio.sleep(0)


async def temp_loop():
    while True:
        try:
            temp = read_and_display_temp()
            water_psi = read_water_pressure()
            # This device owns the water bath state; nothing else emits these.
            # /temperature is omitted when the probe gave nothing, so no
            # listener shows a bath temperature that was never measured.
            msgs = [
                microosc.OscMsg("/water_heater",  [float(state["heater_status"])],  ["f"]),
                microosc.OscMsg("/upper_temp",    [float(config["UPPER_TEMP"])],    ["f"]),
                microosc.OscMsg("/lower_temp",    [float(config["LOWER_TEMP"])],    ["f"]),
                microosc.OscMsg("/water_pressure",[float(water_psi)],               ["f"]),
            ]
            if temp is not None:
                msgs.insert(0, microosc.OscMsg("/temperature", [float(temp)], ["f"]))
            send_to_all(msgs)
            await asyncio.sleep(5)
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__)
            break
    rhb_utils.reboot()


async def main_loop():
    try:
        print("Starting main loop...")
        await asyncio.gather(
            asyncio.create_task(temp_loop()),
            asyncio.create_task(osc_loop()),
            asyncio.create_task(network_loop()),
        )
    except Exception as e:
        print(e)
        rhb_utils.reboot()


# --- Hardware init ---

CONFIG_FILE = "config_rhb.json"
with open(CONFIG_FILE) as f:
    config = json.load(f)

OSC_PORT = 8888
# Long enough for a WiFi client to answer ARP -- a Pico W takes far longer
# than a wired host -- but still bounded so an absent listener cannot stall
# the loop.  The W5500 caches the resolution, so only the first send waits.
SEND_TIMEOUT = 0.5
RX_TIMEOUT = 0.05
RX_BUFFER = 512
MAX_SKIP_CYCLES = 12
_fail_counts = {}
_pressure_seen = [False]
_skip_cycles = {}
HEATER_RESET = 600000
CONNECT_TIMEOUT = 20
CONNECT_RETRY = 60
TEMP_UPPER = config["UPPER_TEMP"]
TEMP_LOWER = config["LOWER_TEMP"]
# Outside this the probe is lying, not reporting a bath anybody could have
TEMP_PLAUSIBLE_LOW = 33
TEMP_PLAUSIBLE_HIGH = 212

state = {
    "heater_status": 0,
    "cooling_down": False,
    "temp_at_heater_start": 0,
    "safety_shutdown": False,
}

pump_pin = digitalio.DigitalInOut(board.IO48)
pump_pin.direction = digitalio.Direction.OUTPUT
pump_pin.value = False

heater_pin = digitalio.DigitalInOut(board.IO47)
heater_pin.direction = digitalio.Direction.OUTPUT
heater_pin.value = False

safety_shutdown_pin = digitalio.DigitalInOut(board.IO3)
safety_shutdown_pin.direction = digitalio.Direction.OUTPUT
safety_shutdown_pin.value = False

pressure_adc = analogio.AnalogIn(board.IO1)

ow = adafruit_onewire.bus.OneWireBus(board.IO15)
ds_sensors = scan_probes()

i2c = busio.I2C(board.IO38, board.IO39)  # SCL=IO38, SDA=IO39
rhb_utils.display = segments.Seg7x4(i2c)
rhb_utils.display.brightness = 1.0

# --- Network / OSC init ---
#
# The network comes up in the background (see network_loop) so the heater
# still runs and the temperature is still displayed when there is no link.

# Receive only.  The accumulator pressure belongs to rhb-sensor-monitor.
dispatch_map = {
    "/pressure": propane_pressure_handler,
}
pool = None
osc_server = None
osc_client = None
mobile_endpoints = []

if rhb_utils.display:
    for i in range(4):
        rhb_utils.display.set_digit_raw(i, 0x40)  # show ----

asyncio.run(main_loop())
