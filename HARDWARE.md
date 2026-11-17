Water Heater Hardware
=====================

The water heater runs entirely from PoE.  A Waveshare ESP32-S3-ETH with
Waveshare's 802.3af PoE module plugs into a carrier board.  The carrier
brings out three SSR control signals, conditions the pressure input and the
DS18B20 bus, and connects the display.  The valve, the heater and the safety
shutdown are switched by SSRs off the board, from their own supplies.

![Water heater circuit](circuit.svg)

[kicad/](kicad/README.md) has a two layer board for it.

Power
-----

    PoE switch (802.3af)
     |
     +-- Cat5 ---- RJ45 on the ESP32-S3-ETH
                    |
                    PoE module ---- 5V on VSYS (pin 39)
                                     |
                                     +-- ESP32-S3, W5500 (their own 3V3)
                                     +-- pressure transducer, 5V
                                     +-- display, probe, from 3V3

The board needs nothing else plugged in.  Buy the board as the
**ESP32-S3-POE-ETH**, which has the module fitted, or fit Waveshare's PoE
module to an ESP32-S3-ETH.  With the loads on SSRs, the board draws a few
watts at most, well inside 802.3af.

- **Never plug in USB-C while PoE is connected.**  A third-party report says
  the PoE module is not isolated from the board, so USB would join the
  host's ground to it.  Unplug the Ethernet to flash, or flash before the
  board goes into the carrier.
- **Check VSYS before fitting the carrier.**  The carrier assumes the PoE
  module's 5V reaches VSYS (pin 39).  That has not been checked against
  Waveshare's schematic or measured.  With PoE connected and nothing on the
  headers, VSYS to GND should read 5V.  If it does not, find the pin that
  does and move `+5V` to it in `kicad/generate_schematic.py`.  Only the
  pressure transducer uses it.

SSR outputs
-----------

Each output is a terminal pair, `SIG` and `GND`, wired to the SSR's DC
input `+` and `-`.  `SIG` is the GPIO itself: 3.3V high, open the SSR.

| Terminal | GPIO | SSR |
| --- | --- | --- |
| J3 `VALVE` | IO48 | Solenoid valve |
| J4 `HEATER` | IO47 | Heater.  Nothing drives IO47 today |
| J5 `SAFETY` | IO3 | Safety shutdown |

R1-R3, 10k from each `SIG` to GND, hold the SSRs off while the ESP32 boots
and its pins float, and if the module is out of its socket.

- **The SSR has to turn on at 3.3V.**  The common DC input SSRs, rated
  3-32V in, do.  One rated 4-32V or 5V in may not, or only some of the
  time.  Check the rating.
- **Input current.**  A typical SSR input takes 5-15 mA, which the ESP32-S3
  drives directly.  An SSR that wants more than about 20 mA needs a
  transistor in front of it.
- **Keep the SSR wiring short and away from the mains side.**  `SIG` is a
  bare GPIO.  Nothing on the board protects it from a wire that touches the
  load's supply.

IO3 is an ESP32-S3 strapping pin, but it only selects the JTAG source, and
only once an eFuse is burned.  The pull-down has no effect on boot.

Sensors
-------

### Pressure, J6

A 0.5-4.5V ratiometric transducer: `+5V`, `SIG`, `GND`.  R4 (10k) and R5
(20k) scale it by 2/3, to 0.33-3.0V, inside the range the ESP32-S3's ADC
reads.  C1 (100nF) filters it.

Use 1% metal film for R4 and R5: the ratio is only as good as the parts,
and 5% ones can put it 3% out.

**Set `PRESSURE_DIVIDER` to 1.5 in `code.py` when this board goes in.**
`read_water_pressure` scales the ADC voltage by it to get the sensor's own
voltage back.  Left at 1.0, pressure reads about a third low across the
whole range.

The sensor is ratiometric, so its output moves with the 5V rail, and the
ESP32-S3's ADC is good to 1-2%.  For a reading closer than a few PSI,
calibrate `PRESSURE_ZERO_V` and `PRESSURE_SPAN_V` against a gauge; the
comment above them in `code.py` says how.  Check `PRESSURE_FULL_PSI`
matches the sensor's rated range.

### Bath probe, J7

The DS18B20: `3V3`, `DQ`, `GND`, powered rather than parasitic.  R6 (4.7k)
pulls DQ up to 3V3.  If the CRC errors in the README persist on a long
cable, try 2.2k for R6 before anything else.

### Display, J2

The HT16K33 backpack, as on the poof controller.  A JST-XH 4 pin, `+ - D C`
left to right: 3V3, GND, SDA (IO39), SCL (IO38).  Run it from 3V3, so the
backpack's own pull-ups on `D` and `C` go to 3V3.

Parts
-----

| Qty | Ref | Part |
| --- | --- | --- |
| 1 | U1 | Waveshare ESP32-S3-POE-ETH (or ESP32-S3-ETH plus its PoE module) |
| 2 | U1 | 1x20 female header, 2.54 mm |
| 3 | R1-R3 | 10k, 1/4 W, 5% or better |
| 1 | R4 | 10k, 1/4 W, 1% metal film |
| 1 | R5 | 20k, 1/4 W, 1% metal film |
| 1 | R6 | 4.7k, 1/4 W, 5% or better |
| 1 | C1 | 100nF ceramic, 5 mm pitch |
| 3 | J3-J5 | Phoenix MKDS 1,5/2-5,08 terminal block |
| 2 | J6, J7 | Phoenix MKDS 1,5/3-5,08 terminal block |
| 1 | J2 | JST B4B-XH-A |
| 4 | | M3 standoffs |
| 3 | | DC input SSRs, 3-32V in, sized for their loads (off board) |
