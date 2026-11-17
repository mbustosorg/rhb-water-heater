Water Heater Carrier Board
==========================

A two layer, 86.5 x 51.5 mm carrier for the circuit in
[HARDWARE.md](../HARDWARE.md).

![Board, top](board.png)

| Ref | Part | Footprint |
| --- | --- | --- |
| U1 | Waveshare ESP32-S3-ETH with PoE module, on 2 x 20 female headers | `rhb:Waveshare_ESP32-S3-ETH_Socketed`, generated |
| R1-R6 | 1/4 W, standing; R4 and R5 1% metal film | `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical` |
| C1 | 100nF | `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` |
| J3-J5 | 2 way screw terminal, 5.08 mm | `TerminalBlock_Phoenix:..._MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` |
| J6, J7 | 3 way screw terminal, 5.08 mm | `TerminalBlock_Phoenix:..._MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal` |
| J2 | JST-XH 4 pin, to the display | `Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` |
| H1-H4 | M3 holes | `MountingHole:MountingHole_3.2mm_M3` |

- **U1** sits component side up, its pin 1 (GPIO20, square pad) at the
  top right.  Its RJ45 and USB-C end overhangs the right edge by about
  16 mm, so the Ethernet cable and the PoE module, which rides over the
  RJ45, are clear of the board.  The footprint is generated from
  Waveshare's drawing: rows 17.78 mm apart, the same positions as a Pico's.
- **Terminals** are all along the bottom edge, wire entry facing off the
  board.  Left to right, with each pin labelled on the silkscreen under the
  block:

  | Block | Pins, left to right |
  | --- | --- |
  | J7 `PROBE` | `GND DQ 3V3` |
  | J6 `PRESSURE` | `GND SIG +5V` |
  | J5 `SAFETY`, J4 `HEATER`, J3 `VALVE` | `GND SIG` |

  The square pad on each block is pin 1, the right-hand pin.
- **J2** is `+ - D C`, left to right, matching the backpack's pins.
- **Ground** is poured on both layers.

Regenerating
------------

The schematic and board are generated; edit the scripts, not the KiCad
files, then run from this directory:

    KICAD=/Applications/KiCad/KiCad.app/Contents
    python3 generate_schematic.py
    $KICAD/MacOS/kicad-cli sch export netlist -o rhb_water_heater.net rhb_water_heater.kicad_sch
    $KICAD/Frameworks/Python.framework/Versions/Current/bin/python3 generate_pcb.py
    $KICAD/Frameworks/Python.framework/Versions/Current/bin/python3 route.py
    $KICAD/MacOS/kicad-cli pcb drc --schematic-parity -o drc.rpt rhb_water_heater.kicad_pcb

`check.sh` runs the first four steps and a placement-only DRC, for
trying out a layout change before routing.

`generate_pcb.py` also writes `rhb.pretty/`, the module's footprint;
`fp-lib-table` points KiCad at it.  `route.py` needs Java 17+ and
`~/tools/freerouting-1.9.jar`.  It autoroutes with freerouting and fills
the ground pours.

DRC reports no clearance, connection or parity errors.  It does list four
expected warnings: the mounting holes are not in the schematic.
