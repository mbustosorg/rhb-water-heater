Red Hot Beverly Water Heater
============================

Circulates the water bath, and owns everything the rest of the rig knows
about it.  Runs on a Waveshare ESP32-S3-ETH (CircuitPython) at 192.168.1.9,
wired -- the W5500 is the only interface, there is no WiFi.

The board switches a pump against a DS18B20 in the bath, reads the loop
pressure, and drives a four digit HT16K33 display.

There is no heater.  `heater_pin` (IO47) is initialised low and nothing
drives it high; the relay is left in the design so it can come back.

OSC messages
------------

Every address has exactly one producer.  This device owns the water bath
state; nothing else on the network emits any of it.  The accumulator
pressure belongs to rhb-sensor-monitor and is consumed here, never
re-broadcast.

| Address | Direction | Payload |
| --- | --- | --- |
| `/temperature` | out | Bath temperature, deg F.  The only temperature on the network |
| `/water_heater` | out | Pump on/off.  Named for the heater it used to switch |
| `/upper_temp`, `/lower_temp` | out | Configured pump setpoints, deg F |
| `/water_pressure` | out | Bath loop pressure, PSI |
| `/pressure` | in, from rhb-sensor-monitor | Accumulator pressure, PSI, rounded |

The five outbound messages go every five seconds, in that order, to every
listener in `MOBILE_CLIENTS`.  `/water_pressure` is last, and rhb-sensor-
monitor writes its `water_*.csv` row when it arrives -- so keep it last.

Addresses are matched exactly.  microosc dispatches on `startswith`, so
`/pressure` alone would also catch `/pressure_fine`; `propane_pressure_
handler` re-checks the address itself.

Display
-------

| Digits | Shows |
| --- | --- |
| 0-1 | Accumulator pressure, from `/pressure` |
| 2-3 | Bath temperature |

`--` on a pair means no data: no `/pressure` has arrived yet, or the probe
gave no usable reading.  The display blinks while the pump is running.

Configuration
-------------

`config_rhb.json`, which is gitignored -- it holds the rig's credentials.

| Key | Meaning |
| --- | --- |
| `IP` | This device's static address |
| `MOBILE_CLIENTS` | Comma separated listeners, `host` or `host:port` |
| `UPPER_TEMP` | Pump off at or above, deg F |
| `LOWER_TEMP` | Pump on at or below, deg F |

The rig is statically addressed and has no DHCP server on the wired side,
so the interface is configured from `IP` directly.  Never call `set_dhcp()`
here: it blocks until it gets a lease that never comes, and with the event
loop behind it that stops the pump as well as the network.

Listeners on a port other than 8888 are written `host:port` -- the body
display is `192.168.1.3:10002`.  Several entries are phones that are absent
most of the time; a listener that fails is skipped for a growing number of
cycles rather than being waited on every time.

Pump control
------------

| Condition | Action |
| --- | --- |
| Temperature at or below `LOWER_TEMP` | Pump on |
| Temperature at or above `UPPER_TEMP` | Pump off |
| Between the two | Whatever it was already doing |
| No usable temperature reading | Pump off |

The band is hysteretic: once running it keeps running until `UPPER_TEMP`,
and once stopped it stays stopped until `LOWER_TEMP`.  With nothing heating
the bath it will normally just circulate.

A missing or unreadable probe is never treated as a temperature.  It used to
come back as 0F, below any setpoint.  Readings outside 33-212F are discarded
for the same reason.

There was a ten minute recycle that latched a safety shutdown when the bath
had not warmed.  It policed the heater, and with no heater the bath only
ever cools, so it would have tripped every time and latched the pump off for
good.  It went with the heater.

Hardware
--------

| Pin | Use |
| --- | --- |
| IO47 | Heater relay, never driven |
| IO48 | Pump relay |
| IO3 | Safety shutdown |
| IO1 | Loop pressure, analogue |
| IO15 | OneWire, DS18B20 bath probe |
| IO38 / IO39 | I2C SCL / SDA, HT16K33 display |

The probe runs at 9 bit resolution.  The reading is used as whole degrees F,
so 12 bit resolves precision that is thrown away and costs 750ms of
conversion per read against 94ms -- with the event loop blocked behind it.

Deployment
----------

Copy `code.py`, `rhb_utils.py` and `config_rhb.json` to the `CIRCUITPY`
volume.  The board soft reboots on write and the relay pins initialise off,
so it fails safe.

The console is on `/dev/cu.usbmodem<UID>`.  Use `cu.*`, not `tty.*`, so DTR
is not asserted.  A healthy board prints `Temperature: NN` about every five
seconds; much longer means something is blocking the event loop.

Known rough edges
-----------------

`/water_heater` reports the pump.  The address kept its name so that
rhb-sensor-monitor's `water_*.csv` and the body display did not have to
change; `state["heater_status"]` is the pump's state for the same reason.

The pump stops on any unusable probe reading, and the OneWire bus throws
CRC errors regularly -- so a flaky probe short cycles the pump.  That
mattered less when the rule was protecting a heater.

The OneWire bus throws CRC errors regularly, and has returned an empty scan
at boot.  The software recovers from both, but the cause is physical --
suspect the pull-up value, parasite power, or cable length before suspecting
the code.

`WIFI_SSID` and `WIFI_PASSWORD` in the config are left over from the Pico W
this replaced.  Nothing reads them.

`read_and_display_temp` keeps the last probe it iterates, so a second sensor
on the bus would be silently ignored.  `scan_probes` logs how many it found.

The receive path overrides two microosc defaults, and needs to.  Its 1ms
socket timeout is shorter than an SPI read of the W5500, and its 128 byte
buffer is smaller than the datagrams that arrive; either one alone stops
`/pressure` from ever being dispatched.  See `poll_osc`.
