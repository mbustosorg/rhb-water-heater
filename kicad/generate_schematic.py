#!/usr/bin/env python3
"""
Generate the KiCad schematic (.kicad_sch) and project (.kicad_pro) for the
water heater carrier board.  ../HARDWARE.md and circuit.svg describe the circuit.

  U1  Waveshare ESP32-S3-ETH, socketed, with Waveshare's 802.3af PoE module
      fitted.  PoE is the only supply: the module's 5V comes out on VSYS.
  J3  SSR input, solenoid valve      IO48
  J4  SSR input, heater              IO47 (not driven today)
  J5  SSR input, safety shutdown     IO3
      Each is the 3.3V GPIO and GND, with a 10k pull-down (R1-R3) so the
      SSR stays off while the ESP32 boots.  The SSRs switch the loads off
      board.
  R4/R5  10k / 20k divider, 0.5-4.5V pressure transducer -> 0.33-3.0V on IO1
  R6  4.7k DS18B20 pull-up to 3V3, on IO15
  J2  JST-XH 4 pin to the HT16K33 backpack: +, -, D, C  (IO39 SDA, IO38 SCL)

Connectivity is label-based.  build.sh runs this and exports the netlist.
"""
import json
import os
import uuid

PROJECT   = "rhb_water_heater"
ROOT_UUID = "00000000-0000-0000-0000-0000000000a1"  # stable root sheet uuid

def U(): return str(uuid.uuid4())

# --------------------------------------------------------------------------
# low-level emitters
# --------------------------------------------------------------------------
out = []
def emit(s): out.append(s)

def label(net, x, y, justify):
    emit(f'  (label "{net}" (at {x:.3f} {y:.3f} 0)\n'
         f'    (effects (font (size 1.27 1.27)) (justify {justify}))\n'
         f'    (uuid "{U()}"))')

def wire(x1, y1, x2, y2):
    emit(f'  (wire (pts (xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f}))\n'
         f'    (stroke (width 0) (type default)) (uuid "{U()}"))')

def text(s, x, y, size=1.8):
    esc = s.replace('"', '\\"')
    emit(f'  (text "{esc}" (at {x:.3f} {y:.3f} 0)\n'
         f'    (effects (font (size {size} {size})) (justify left)) (uuid "{U()}"))')

def no_connect(x, y):
    emit(f'  (no_connect (at {x:.3f} {y:.3f}) (uuid "{U()}"))')

# --------------------------------------------------------------------------
# symbol model (rectangular block with left / right pin lists)
# --------------------------------------------------------------------------
PIN_LEN = 5.08
PITCH   = 2.54

lib_symbols = []
symbol_pins = {}   # libname -> { pin_number_str: (tip_x_sym, tip_y_sym, side) }

def make_block(libname, left, right, hw=7.62, value="", ref="U"):
    base = libname.split(":")[-1]
    n    = max(len(left), len(right))
    top  = (n - 1) / 2 * PITCH
    half_h = top + PITCH
    offs   = {}

    body = (f'    (symbol "{base}_0_1"\n'
            f'      (rectangle (start {-hw:.3f} {half_h:.3f}) (end {hw:.3f} {-half_h:.3f})\n'
            f'        (stroke (width 0.254) (type default)) (fill (type background))))')
    pin_sx = []
    for side, pins, tip, angle in (("L", left, -(hw + PIN_LEN), 0),
                                   ("R", right, hw + PIN_LEN, 180)):
        for i, p in enumerate(pins):
            if p is None: continue
            num, name, etype = p
            sy = top - i * PITCH
            pin_sx.append(
                f'      (pin {etype} line (at {tip:.3f} {sy:.3f} {angle}) (length {PIN_LEN})\n'
                f'        (name "{name}" (effects (font (size 1.27 1.27))))\n'
                f'        (number "{num}" (effects (font (size 1.27 1.27)))))')
            offs[num] = (tip, sy, side)
    sym = (f'  (symbol "{libname}"\n'
           f'    (exclude_from_sim no) (in_bom yes) (on_board yes)\n'
           f'    (property "Reference" "{ref}" (at {-hw:.3f} {half_h+2.54:.3f} 0)\n'
           f'      (effects (font (size 1.27 1.27)) (justify left)))\n'
           f'    (property "Value" "{value}" (at {-hw:.3f} {-(half_h+2.54):.3f} 0)\n'
           f'      (effects (font (size 1.27 1.27)) (justify left)))\n'
           f'    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
           f'    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
           f'{body}\n'
           f'    (symbol "{base}_1_1"\n' + "\n".join(pin_sx) + "\n    )\n  )")
    lib_symbols.append(sym)
    symbol_pins[libname] = offs

def make_passive(libname, graphic, ref):
    """2-pin vertical passive.  Pin 1 tip at the top, pin 2 at the bottom.

    For the diode pin 1 is the cathode, matching KiCad's DO-41 footprint.
    For the polarised capacitor pin 1 is +.
    """
    base = libname.split(":")[-1]
    TIP  = PIN_LEN + PITCH   # = 7.62
    if graphic == "R":
        gfx = ('      (rectangle (start -1.016 2.54) (end 1.016 -2.54)\n'
               '        (stroke (width 0.254) (type default)) (fill (type none)))')
    elif graphic == "C":
        gfx = ('      (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762))\n'
               '        (stroke (width 0.508) (type default)) (fill (type none)))\n'
               '      (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762))\n'
               '        (stroke (width 0.508) (type default)) (fill (type none)))\n'
               '      (polyline (pts (xy 0 2.54) (xy 0 0.762))\n'
               '        (stroke (width 0) (type default)) (fill (type none)))\n'
               '      (polyline (pts (xy 0 -0.762) (xy 0 -2.54))\n'
               '        (stroke (width 0) (type default)) (fill (type none)))')
    elif graphic == "F":
        gfx = ('      (rectangle (start -0.762 2.54) (end 0.762 -2.54)\n'
               '        (stroke (width 0.254) (type default)) (fill (type none)))\n'
               '      (polyline (pts (xy 0 2.54) (xy 0 -2.54))\n'
               '        (stroke (width 0) (type default)) (fill (type none)))')
    else:  # D, cathode bar at the top, pointing up from the anode
        gfx = ('      (polyline (pts (xy -1.27 -1.27) (xy 1.27 -1.27) (xy 0 1.27) (xy -1.27 -1.27))\n'
               '        (stroke (width 0.254) (type default)) (fill (type none)))\n'
               '      (polyline (pts (xy -1.27 1.27) (xy 1.27 1.27))\n'
               '        (stroke (width 0.254) (type default)) (fill (type none)))\n'
               '      (polyline (pts (xy 0 2.54) (xy 0 -2.54))\n'
               '        (stroke (width 0) (type default)) (fill (type none)))')
    names = {"D": ("K", "A"), "C": ("+", "-")}.get(graphic, ("~", "~"))
    sym = (f'  (symbol "{libname}"\n'
           f'    (exclude_from_sim no) (in_bom yes) (on_board yes)\n'
           f'    (property "Reference" "{ref}" (at 2.54 0 90)\n'
           f'      (effects (font (size 1.27 1.27))))\n'
           f'    (property "Value" "" (at -2.54 0 90) (effects (font (size 1.27 1.27))))\n'
           f'    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
           f'    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
           f'    (symbol "{base}_0_1"\n{gfx}\n'
           f'      (pin passive line (at 0 {TIP:.3f} 270) (length {PIN_LEN})\n'
           f'        (name "{names[0]}" (effects (font (size 1.27 1.27))))\n'
           f'        (number "1" (effects (font (size 1.27 1.27)))))\n'
           f'      (pin passive line (at 0 {-TIP:.3f} 90) (length {PIN_LEN})\n'
           f'        (name "{names[1]}" (effects (font (size 1.27 1.27))))\n'
           f'        (number "2" (effects (font (size 1.27 1.27)))))\n'
           f'    )\n  )')
    lib_symbols.append(sym)
    symbol_pins[libname] = {"1": (0.0, TIP, "T"), "2": (0.0, -TIP, "B")}

# --------------------------------------------------------------------------
# placement
# --------------------------------------------------------------------------
def place(libname, ref, value, footprint, px, py, net_map):
    """Place a symbol; pins in net_map get a stub and a label, the rest a no-connect"""
    offs = symbol_pins[libname]
    # Snap to the 2.54 grid so every pin tip lands on the connection grid
    px, py = round(px / PITCH) * PITCH, round(py / PITCH) * PITCH
    emit(f'  (symbol (lib_id "{libname}") (at {px:.3f} {py:.3f} 0) (unit 1)\n'
         f'    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
         f'    (uuid "{U()}")\n'
         f'    (property "Reference" "{ref}" (at {px+4:.3f} {py-12:.3f} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (justify left)))\n'
         f'    (property "Value" "{value}" (at {px+4:.3f} {py-9:.3f} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (justify left)))\n'
         f'    (property "Footprint" "{footprint}" (at {px:.3f} {py:.3f} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (hide yes)))\n'
         f'    (property "Datasheet" "~" (at {px:.3f} {py:.3f} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (hide yes)))\n'
         f'    (instances (project "{PROJECT}"\n'
         f'      (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))\n'
         f'  )')
    for num, (sx, sy, side) in offs.items():
        ax, ay = px + sx, py - sy   # schematic coords (Y flipped)
        net = net_map.get(num)
        if net is None:
            no_connect(ax, ay)
            continue
        if   side == "L": lx, ly, just = ax - PITCH, ay, "right"
        elif side == "R": lx, ly, just = ax + PITCH, ay, "left"
        elif side == "T": lx, ly, just = ax, ay - PITCH, "left"
        else:             lx, ly, just = ax, ay + PITCH, "left"
        wire(ax, ay, lx, ly)
        label(net, lx, ly, just)

# --------------------------------------------------------------------------
# library symbols
# --------------------------------------------------------------------------
def pin(n, name, t="passive"): return (str(n), name, t)
def io(n, name): return pin(n, name, "bidirectional")

# Waveshare's numbering: 1-20 down one side from the USB end, 21-40 back up
# the other.  The same positions as a Pico's pins.
make_block("rhb_water_heater:ESP32-S3-ETH",
    left=[
        io(1, "GPIO20"), io(2, "GPIO19"), pin(3, "GND"),   io(4, "GPIO48"),
        io(5, "GPIO47"), io(6, "GPIO46"), io(7, "GPIO45"), pin(8, "GND"),
        io(9, "GPIO42"), io(10, "GPIO41"), io(11, "GPIO40"), io(12, "GPIO39"),
        pin(13, "GND"),  io(14, "GPIO38"), io(15, "GPIO37"), io(16, "GPIO36"),
        io(17, "GPIO35"), pin(18, "GND"),  io(19, "GPIO34"), io(20, "GPIO33"),
    ],
    right=[
        pin(40, "VBUS", "power_in"),  pin(39, "VSYS", "power_out"),
        pin(38, "GND"),               pin(37, "3V3_EN", "input"),
        pin(36, "3V3", "power_out"),  io(35, "GPIO21"),
        io(34, "GPIO17"),             pin(33, "GND"),
        io(32, "GPIO16"),             io(31, "GPIO18"),
        pin(30, "CHIP_UP", "input"),  io(29, "GPIO15"),
        pin(28, "GND"),               io(27, "GPIO3"),
        io(26, "GPIO2"),              io(25, "GPIO1"),
        io(24, "GPIO0"),              pin(23, "GND"),
        io(22, "GPIO44"),             io(21, "GPIO43"),
    ],
    hw=10.16, value="Waveshare ESP32-S3-ETH + PoE module")

make_block("rhb_water_heater:Term2",
    left=[], right=[pin(1, "SSR+"), pin(2, "SSR-")],
    hw=5.08, value="", ref="J")

make_block("rhb_water_heater:Term3",
    left=[], right=[pin(1, "1"), pin(2, "2"), pin(3, "3")],
    hw=5.08, value="", ref="J")

make_block("rhb_water_heater:Display4",
    left=[pin(1, "+"), pin(2, "-"), pin(3, "D"), pin(4, "C")],
    right=[], hw=5.08, value="HT16K33 display", ref="J")

make_passive("rhb_water_heater:R",  "R", "R")
make_passive("rhb_water_heater:C",  "C", "C")

# --------------------------------------------------------------------------
# footprints
# --------------------------------------------------------------------------
FP_MODULE = "rhb_water_heater:Waveshare_ESP32-S3-ETH_Socketed"
FP_R      = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"
FP_C      = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_T2     = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
FP_T3     = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal"
FP_JST4   = "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical"

# --------------------------------------------------------------------------
# schematic layout  (mm, Y down)
# --------------------------------------------------------------------------
text("RHB water heater carrier", 20, 15, size=3)
text("Powered only by PoE: Waveshare 802.3af module on the ESP32-S3-ETH, 5V out on VSYS", 20, 21, size=1.5)
text("The valve, heater and safety loads are switched by SSRs off board; this board drives their inputs", 20, 25, size=1.5)

text("=== ESP32-S3-ETH ===", 20, 40)
place("rhb_water_heater:ESP32-S3-ETH", "U1", "Waveshare ESP32-S3-ETH + PoE module", FP_MODULE,
      55, 90,
      {
          "4":  "VALVE",       # IO48
          "5":  "HEATER",      # IO47
          "12": "SDA",         # IO39
          "14": "SCL",         # IO38
          "25": "PRESS_ADC",   # IO1
          "27": "SAFETY",      # IO3
          "29": "DQ",          # IO15
          "36": "+3V3",
          "39": "+5V",         # VSYS: the PoE module's 5V
          "3": "GND", "8": "GND", "13": "GND", "18": "GND",
          "23": "GND", "28": "GND", "33": "GND", "38": "GND",
      })

text("=== SSR OUTPUTS ===", 110, 40)
CHANNELS = [  # gpio net, pull-down, terminal, terminal value
    ("VALVE",  "R1", "J3", "Valve SSR: signal, GND"),
    ("HEATER", "R2", "J4", "Heater SSR: signal, GND"),
    ("SAFETY", "R3", "J5", "Safety SSR: signal, GND"),
]
for i, (name, rpd, j, jval) in enumerate(CHANNELS):
    x0, y0 = 120, 65 + i * 30
    place("rhb_water_heater:R", rpd, "10k", FP_R, x0, y0 + 5, {"1": name, "2": "GND"})
    place("rhb_water_heater:Term2", j, jval, FP_T2, x0 + 30, y0, {"1": name, "2": "GND"})

text("=== SENSORS ===", 20, 160)
place("rhb_water_heater:Term3", "J6", "Pressure: +5V, signal, GND", FP_T3, 25, 185,
      {"1": "+5V", "2": "PRESS_IN", "3": "GND"})
place("rhb_water_heater:R", "R4", "10k", FP_R, 50, 180, {"1": "PRESS_IN", "2": "PRESS_ADC"})
place("rhb_water_heater:R", "R5", "20k", FP_R, 60, 190, {"1": "PRESS_ADC", "2": "GND"})
place("rhb_water_heater:C", "C1", "100nF", FP_C, 70, 190, {"1": "PRESS_ADC", "2": "GND"})
text("0.5-4.5V in -> 0.33-3.0V at IO1 (x 2/3)", 20, 200, size=1.3)

place("rhb_water_heater:Term3", "J7", "DS18B20: 3V3, DQ, GND", FP_T3, 25, 220,
      {"1": "+3V3", "2": "DQ", "3": "GND"})
place("rhb_water_heater:R", "R6", "4.7k", FP_R, 50, 220, {"1": "+3V3", "2": "DQ"})

text("=== DISPLAY ===", 110, 170)
text("HT16K33 backpack at 0x70, run from 3V3", 110, 174, size=1.3)
place("rhb_water_heater:Display4", "J2", "HT16K33 display", FP_JST4, 130, 190,
      {"1": "+3V3", "2": "GND", "3": "SDA", "4": "SCL"})

# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def write_schematic(path):
    header = f'''\
(kicad_sch
  (version 20231120)
  (generator "rhb_water_heater_gen")
  (uuid "{ROOT_UUID}")
  (paper "A3")
  (lib_symbols
{chr(10).join(lib_symbols)}
  )
'''
    with open(path, "w") as f:
        f.write(header + "\n".join(out) + "\n)\n")
    print(f"Wrote {path}")

def write_project(path):
    proj = {
        "board": {"design_settings": {}, "layer_presets": [], "viewports": []},
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "erc": {"erc_exclusions": [], "meta": {"version": 0}, "pin_map": [], "rule_severities": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 1},
        "net_settings": {"classes": [], "meta": {"version": 3}, "net_colors": None,
                         "netclass_assignments": None, "netclass_patterns": []},
        "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [], "text_variables": {}
    }
    with open(path, "w") as f:
        json.dump(proj, f, indent=2)
    print(f"Wrote {path}")

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
write_schematic(os.path.join(OUT_DIR, f"{PROJECT}.kicad_sch"))
write_project(  os.path.join(OUT_DIR, f"{PROJECT}.kicad_pro"))
