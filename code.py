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

def manage_valve(temp):
    """Open the solenoid valve while the bath is cold.

    This board drives the valve on IO48 and nothing else.  There is still a
    heater in the system, but something else controls it: heater_pin is
    initialised low and never driven high here.

    state["heater_status"] is the valve's state despite the name.  It is what
    /water_heater carries, and rhb-sensor-monitor and the body display
    already key on that address.

    There was a ten minute recycle here that latched safety_shutdown when the
    bath had not warmed.  It policed a heater this board no longer owns, and
    it cannot tell a heater fault from a valve that is doing its job, so it
    went with the heater.
    """
    try:
        if state["safety_shutdown"]:
            valve_pin.value = False
            safety_shutdown_pin.value = True
            return
        if state["heater_status"] and temp >= TEMP_UPPER:
            state["heater_status"] = 0
            valve_pin.value = False
            print("Valve closed")
        elif not state["heater_status"] and temp <= TEMP_LOWER:
            state["heater_status"] = supervisor.ticks_ms()
            state["temp_at_heater_start"] = temp
            valve_pin.value = True
            print("Valve open")
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


def shutdown_valve(reason):
    """Close the valve.  Safe to call from any state."""
    if state["heater_status"] or valve_pin.value:
        print(f"Valve closed: {reason}")
    state["heater_status"] = 0
    valve_pin.value = False


def show_bath_digits():
    """Draw the bath temperature on digits 2 and 3, blanked on the off beat.

    They blink while the valve is open.  The HT16K33's own blink_rate cannot
    do that: it blinks the whole display, the pressure digits included.  So
    blink_loop flips _blink_off and redraws, and this blanks just these two.
    """
    if not rhb_utils.display:
        return
    temp = _bath_temp[0]
    if state["heater_status"] and _blink_off[0]:
        glyphs = (0x00, 0x00)
    elif temp is None:
        glyphs = (0x40, 0x40)  # --, no reading
    else:
        rhb_utils.display[2] = str((temp // 10) % 10)
        rhb_utils.display[3] = str(temp % 10)
        return
    for i, glyph in zip((2, 3), glyphs):
        rhb_utils.display.set_digit_raw(i, glyph)


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
    is below TEMP_LOWER, so manage_valve would open the valve on a
    temperature nobody measured.  No reading means the valve closes.
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
        shutdown_valve("no usable temperature reading")
        _bath_temp[0] = None
        show_bath_digits()
        return None
    print(f"Temperature: {temp}")
    manage_valve(temp)
    _bath_temp[0] = temp
    show_bath_digits()
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


async def blink_loop():
    """Blink the bath digits at 1Hz while the valve is open.

    Nothing to undo when it closes: read_and_display_temp redraws straight
    after manage_valve, and show_bath_digits only blanks while it is open.
    """
    while True:
        await asyncio.sleep(BLINK_HALF_PERIOD)
        _blink_off[0] = not _blink_off[0]
        if state["heater_status"]:
            show_bath_digits()


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
            asyncio.create_task(blink_loop()),
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
_bath_temp = [None]
_blink_off = [False]
BLINK_HALF_PERIOD = 0.5
CONNECT_TIMEOUT = 20
CONNECT_RETRY = 60
TEMP_UPPER = config["UPPER_TEMP"]
TEMP_LOWER = config["LOWER_TEMP"]
# Outside this the probe is lying, not reporting a bath anybody could have
TEMP_PLAUSIBLE_LOW = 33
TEMP_PLAUSIBLE_HIGH = 212

state = {
    # Named for the address it is published on, /water_heater.  It is the
    # valve's state; see manage_valve.
    "heater_status": 0,
    "temp_at_heater_start": 0,
    "safety_shutdown": False,
}

valve_pin = digitalio.DigitalInOut(board.IO48)
valve_pin.direction = digitalio.Direction.OUTPUT
valve_pin.value = False

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
