Red Hot Beverly Water Heater
============================

Controls the water bath's solenoid valve from a DS18B20 in the bath, reads
the loop pressure, and drives a four digit HT16K33 display.  CircuitPython on
a Waveshare ESP32-S3-ETH at 192.168.1.9, wired; there is no WiFi.

The heater relay (`heater_pin`, IO47) is initialised low and never driven;
the heater is controlled elsewhere.

OSC messages
------------

Every address has one producer.  `/pressure` is consumed here, never
re-broadcast.

| Address | Direction | Payload |
| --- | --- | --- |
| `/temperature` | out | Bath temperature, deg F.  The only temperature on the network |
| `/water_heater` | out | Valve open/shut.  Named for the heater it used to switch |
| `/upper_temp`, `/lower_temp` | out | Configured valve setpoints, deg F |
| `/water_pressure` | out | Bath loop pressure, PSI |
| `/pressure` | in, from rhb-sensor-monitor | Accumulator pressure, PSI, rounded |

The outbound messages go every 5 s, in that order, to `MOBILE_CLIENTS`.  Keep
`/water_pressure` last: rhb-sensor-monitor writes its `water_*.csv` row when
it arrives.

microosc dispatches on `startswith`, so `propane_pressure_handler` re-checks
the address to ignore `/pressure_fine`.

Display
-------

| Digits | Shows |
| --- | --- |
| 0-1 | Accumulator pressure, from `/pressure` |
| 2-3 | Bath temperature, blinking while the valve is open |

`--` means no data.

Configuration
-------------

`config_rhb.json`, gitignored.

| Key | Meaning |
| --- | --- |
| `IP` | This device's static address |
| `MOBILE_CLIENTS` | Comma separated listeners, `host` or `host:port` (body display is `192.168.1.3:10002`) |
| `UPPER_TEMP` | Valve shuts at or above, deg F |
| `LOWER_TEMP` | Valve opens at or below, deg F |

Never call `set_dhcp()`: the rig has no DHCP, and it blocks the event loop,
valve included, waiting for a lease.

A listener that fails, usually an absent phone, is skipped for a growing
number of cycles.

Valve control
-------------

| Condition | Action |
| --- | --- |
| Temperature at or below `LOWER_TEMP` | Valve opens |
| Temperature at or above `UPPER_TEMP` | Valve shuts |
| Between the two | No change |
| No usable temperature reading | Valve shuts |

Readings outside 33-212F are discarded; a missing probe used to read as 0F.

The old ten minute recycle safety shutdown policed the heater, which this
board no longer owns, so it was removed.

Hardware
--------

| Pin | Use |
| --- | --- |
| IO47 | Heater SSR, not driven |
| IO48 | Valve SSR |
| IO3 | Safety shutdown SSR |
| IO1 | Loop pressure, analogue |
| IO15 | OneWire, DS18B20 bath probe |
| IO38 / IO39 | I2C SCL / SDA, HT16K33 display |

Powered by PoE alone, on a carrier board; the SSRs are off the board.  See
[HARDWARE.md](HARDWARE.md) and [kicad/](kicad/README.md).  **Set
`PRESSURE_DIVIDER` in `code.py` to 1.5 when the carrier goes in.**

The probe runs at 9 bit: readings are used as whole degrees, and 12 bit
blocks the event loop 750 ms per read instead of 94 ms.

Deployment
----------

Copy `code.py`, `rhb_utils.py` and `config_rhb.json` to `CIRCUITPY`.  The
board soft reboots on write and the relay pins initialise off.

Console: `/dev/cu.usbmodem<UID>` (`cu.*`, not `tty.*`, so DTR is not
asserted).  A healthy board prints `Temperature: NN` about every 5 s.

Known rough edges
-----------------

- `/water_heater` and `state["heater_status"]` report the valve, kept so
  rhb-sensor-monitor and the body display didn't have to change.
- The valve shuts on any unusable probe reading, and the OneWire bus throws
  CRC errors regularly, so a flaky probe cycles the valve.
- The OneWire bus has also returned an empty scan at boot.  The software
  recovers, but suspect the pull-up, parasite power or cable length first.
- `read_and_display_temp` keeps the last probe on the bus, so a second one is
  ignored.  `scan_probes` logs how many it found.
- The receive path overrides microosc's 1 ms socket timeout and 128 byte
  buffer; either default alone stops `/pressure` arriving.  See `poll_osc`.
