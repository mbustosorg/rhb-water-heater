#!/usr/bin/env python3
"""
Place the water heater carrier board.  Run with KiCad's bundled python after
exporting the netlist from the schematic:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 generate_pcb.py

Reads:  rhb_water_heater.net
Writes: rhb.pretty/Waveshare_ESP32-S3-ETH_Socketed.kicad_mod
        rhb_water_heater.kicad_pcb (unrouted; see README.md for routing)

Layout, 2 layers:
  - The ESP32-S3-ETH runs along the top, socketed, with its RJ45 / USB-C end
    hanging off the right edge.  The PoE module rides on top of it, over the
    RJ45, so nothing on this board is under the PoE circuitry.
  - The display connector, J2, and the title are in the space left of the
    module's far end.
  - Every terminal is along the bottom edge, wire entry facing off the
    board: the probe and the pressure transducer on the left, then the
    three SSR inputs, safety, heater and valve.  Each one's resistors stand
    just above it.
  - The ground pour is on both layers.
  - M3 holes in the four corners.
"""
import json
import os
import re
import sys

NET    = "rhb_water_heater.net"
PCB    = "rhb_water_heater.kicad_pcb"
PRO    = "rhb_water_heater.kicad_pro"
FPROOT = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
HERE   = os.path.dirname(os.path.abspath(__file__))
LOCAL  = os.path.join(HERE, "rhb.pretty")

try:
    import pcbnew
except ImportError:
    sys.exit("ERROR: run with KiCad's bundled python3 (pcbnew not found).")

try:
    import wx; _APP = wx.App()
except Exception as _e:
    print("warning: wx init:", _e)

MM = pcbnew.FromMM
def V(x, y): return pcbnew.VECTOR2I(MM(x), MM(y))

PITCH = 2.54

# ── module footprint ─────────────────────────────────────────────────────────
# Waveshare ESP32-S3-ETH, top view, USB / RJ45 end to the right.  Origin at
# pin 1 (GPIO20).  Pins 1-20 run right to left along y = 0, pins 21-40 left
# to right along y = 17.78, so pin 40 (VBUS) is opposite pin 1 -- the same
# positions as a Pico's.  From Waveshare's drawing: 72.8 x 21 mm, the pin 1
# column 19.87 mm from the USB end.
MOD_USB_END = 19.87            # module edge, right of pin 1
MOD_FAR_END = -(72.80 - 19.87) # module edge, past pin 20
MOD_TOP     = -(21.00 - 17.78) / 2
MOD_BOT     = 17.78 - MOD_TOP
ROW_B       = 17.78
OVERHANG_AT = 3.5              # where the carrier's edge cuts across it

def module_pin_xy(n):
    if n <= 20:
        return (-(n - 1) * PITCH, 0.0)
    return (-(40 - n) * PITCH, ROW_B)

def write_module_footprint(path):
    def line(x0, y0, x1, y1, layer, w):
        return (f'  (fp_line (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f})\n'
                f'    (stroke (width {w}) (type solid)) (layer "{layer}"))')
    def rect(x0, y0, x1, y1, layer, w):
        return (f'  (fp_rect (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f})\n'
                f'    (stroke (width {w}) (type solid)) (fill no) (layer "{layer}"))')
    def txt(kind, s, x, y, layer, size=1.0, hide=False):
        h = " (hide yes)" if hide else ""
        return (f'  (property "{kind}" "{s}" (at {x:.3f} {y:.3f} 0) (layer "{layer}"){h}\n'
                f'    (effects (font (size {size} {size}) (thickness {size*0.15:.3f}))))')
    def gtext(s, x, y, layer, size=1.0):
        return (f'  (fp_text user "{s}" (at {x:.3f} {y:.3f} 0) (layer "{layer}")\n'
                f'    (effects (font (size {size} {size}) (thickness {size*0.15:.3f}))))')

    items = [
        '(footprint "Waveshare_ESP32-S3-ETH_Socketed"',
        '  (version 20240108) (generator "rhb_water_heater_gen")',
        '  (layer "F.Cu")',
        '  (descr "Waveshare ESP32-S3-ETH on two 1x20 2.54 mm female headers, '
        '17.78 mm apart.  RJ45 and USB-C end overhangs the carrier; '
        'https://www.waveshare.com/wiki/ESP32-S3-ETH")',
        '  (tags "ESP32-S3 W5500 Ethernet PoE Waveshare Pico")',
        '  (attr through_hole)',
        txt("Reference", "REF**", -24.0, 8.89, "F.SilkS"),
        txt("Value", "Waveshare_ESP32-S3-ETH", -24.0, 11.5, "F.Fab"),
        txt("Footprint", "", 0, 0, "F.Fab", hide=True),
        txt("Datasheet", "", 0, 0, "F.Fab", hide=True),
        txt("Description", "", 0, 0, "F.Fab", hide=True),
        # The whole module, on Fab
        rect(MOD_FAR_END, MOD_TOP, MOD_USB_END, MOD_BOT, "F.Fab", 0.1),
        gtext("RJ45 + USB-C", 11.7, 8.89, "F.Fab", 1.0),
        # The part over the carrier, on silk
        line(MOD_FAR_END, MOD_TOP - 0.2, OVERHANG_AT - 0.6, MOD_TOP - 0.2, "F.SilkS", 0.12),
        line(MOD_FAR_END, MOD_BOT + 0.2, OVERHANG_AT - 0.6, MOD_BOT + 0.2, "F.SilkS", 0.12),
        line(MOD_FAR_END - 0.2, MOD_TOP - 0.2, MOD_FAR_END - 0.2, MOD_BOT + 0.2, "F.SilkS", 0.12),
        gtext("ESP32-S3-ETH  RJ45 >>", -24.0, 6.0, "F.SilkS", 1.2),
        gtext("1", 0, -2.6, "F.SilkS", 0.8),
        gtext("40", 0, ROW_B + 2.6, "F.SilkS", 0.8),
        # Courtyard stops at the carrier edge
        rect(MOD_FAR_END - 0.5, MOD_TOP - 0.5, OVERHANG_AT, MOD_BOT + 0.5, "F.CrtYd", 0.05),
    ]
    for n in range(1, 41):
        x, y = module_pin_xy(n)
        shape = "rect" if n == 1 else "circle"
        items.append(f'  (pad "{n}" thru_hole {shape} (at {x:.3f} {y:.3f}) (size 1.7 1.7)\n'
                     f'    (drill 1.0) (layers "*.Cu" "*.Mask"))')
    items.append(')')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(items) + "\n")
    print(f"wrote {path}")

write_module_footprint(os.path.join(LOCAL, "Waveshare_ESP32-S3-ETH_Socketed.kicad_mod"))

# ── parse netlist ────────────────────────────────────────────────────────────
src = open(NET).read()

comp_fp, comp_val = {}, {}
for ref, body in re.findall(
        r'\(comp\s+\(ref "([^"]+)"\)(.*?)(?=\(comp\s|\(libparts\b|\Z)', src, re.S):
    fp  = re.search(r'\(footprint "([^"]+)"\)', body)
    val = re.search(r'\(value "([^"]*)"\)', body)
    if fp:  comp_fp[ref]  = fp.group(1)
    if val: comp_val[ref] = val.group(1)

pad_net, netnames = {}, set()
for name, body in re.findall(
        r'\(net\s+\(code "\d+"\)\s+\(name "([^"]+)"\)(.*?)(?=\(net\s|\Z)', src, re.S):
    for ref, pin in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', body):
        pad_net[(ref, pin)] = name
        netnames.add(name)

print(f"parsed {len(comp_fp)} components, {len(netnames)} nets, {len(pad_net)} pad-nets")

# ── board setup ──────────────────────────────────────────────────────────────
board = pcbnew.CreateEmptyBoard()
board.SetCopperLayerCount(2)

net_items = {}
for n in sorted(netnames):
    ni = pcbnew.NETINFO_ITEM(board, n)
    board.Add(ni); net_items[n] = ni

def load_fp(fpid):
    lib, name = fpid.split(":", 1)
    root = LOCAL if lib == "rhb" else os.path.join(FPROOT, lib + ".pretty")
    fp = pcbnew.FootprintLoad(root, name)
    if fp is None:
        sys.exit(f"ERROR: footprint {fpid} not found")
    return fp

placed = {}
def add(ref, x, y, rot=0):
    """Place a footprint with its origin, pad 1 for every part here, at (x, y).

    rot is CCW degrees (KiCad convention).
    """
    fp = load_fp(comp_fp[ref])
    fp.SetFPID(pcbnew.LIB_ID(*comp_fp[ref].split(":", 1)))
    fp.SetReference(ref)
    fp.SetValue(comp_val.get(ref, ""))
    fp.SetPosition(V(x, y))
    if rot:
        fp.SetOrientationDegrees(rot)
    board.Add(fp)
    for pad in fp.Pads():
        key = (ref, pad.GetNumber())
        if key in pad_net:
            pad.SetNet(net_items[pad_net[key]])
    placed[ref] = fp
    return fp

def ref_at(ref, x, y, rot=0):
    r = placed[ref].Reference()
    r.SetPosition(V(x, y))
    r.SetTextAngleDegrees(rot)

def add_mh(ref, cx, cy):
    fp = load_fp("MountingHole:MountingHole_3.2mm_M3")
    fp.SetReference(ref)
    fp.SetValue("M3")
    fp.SetPosition(V(cx, cy))
    fp.Reference().SetVisible(False)
    board.Add(fp)

def set_rect(zone, x0, y0, x1, y1):
    sps = zone.Outline(); sps.NewOutline()
    for px, py in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        sps.Append(MM(px), MM(py))

def silk(s, x, y, size=1.0, rot=0, layer=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer if layer is not None else pcbnew.F_SilkS)
    t.SetPosition(V(x, y))
    t.SetTextSize(V(size, size))
    t.SetTextThickness(MM(size * 0.15))
    if rot:
        t.SetTextAngleDegrees(rot)
    board.Add(t)

def silk_rect(x0, y0, x1, y1, w=0.12):
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetLayer(pcbnew.F_SilkS)
    r.SetWidth(MM(w))
    r.SetStart(V(x0, y0)); r.SetEnd(V(x1, y1))
    board.Add(r)

# ── floorplan ────────────────────────────────────────────────────────────────
# Module pin 1 at (PX, PY).  Its rows are at PY and PY + 17.78, running left
# to PX - 48.26; its USB / RJ45 end overhangs the right edge.
PX, PY = 150.0, 100.0

BX0 = 67.0
BX1 = PX + OVERHANG_AT
BY0 = 90.5
BY1 = 142.0
CORNER_R = 2.0
MH_INSET = 3.5

add("U1", PX, PY)
ref_at("U1", PX - 36.0, PY + 8.89)

# Display connector left of the module.  Pins + - D C run left to right.
add("J2", 76.0, 104.0)
ref_at("J2", 72.0, 104.0)
# Its GND pad sits between SDA/SCL and 3V3 at 2.5 mm pitch, where a thermal
# relief only gets one spoke in; connect it solid.
for pad in placed["J2"].Pads():
    if pad.GetNumber() == "2":
        pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
silk("+  -  D  C", 79.75, 108.3, 0.9)
silk("DISPLAY", 79.75, 100.3, 0.9)
silk("RHB WATER HEATER", 81.5, 113.5, 1.2)
silk("PoE only.", 81.5, 116.0, 0.8)
silk("No USB with PoE.", 81.5, 117.6, 0.8)

# ── terminals, along the bottom ──────────────────────────────────────────────
# Rotated 180 so the wire entry faces off the bottom edge; pin 1 is then on
# the right.  Contiguous 5.08 mm pitch, 1.5 mm between blocks.
TERM_Y = BY1 - 6.0
PARTS_Y = TERM_Y - 9.5
TERMS = [  # pin 1 x, ref, label, pin names right to left
    (143.00, "J3", "VALVE",    ("SIG", "GND")),
    (131.34, "J4", "HEATER",   ("SIG", "GND")),
    (119.68, "J5", "SAFETY",   ("SIG", "GND")),
    (108.02, "J6", "PRESSURE", ("+5V", "SIG", "GND")),
    ( 91.28, "J7", "PROBE",    ("3V3", "DQ", "GND")),
]
for tx, j, name, pins in TERMS:
    add(j, tx, TERM_Y, rot=180)
    placed[j].Reference().SetVisible(False)
    mid = tx - (len(pins) - 1) * 5.08 / 2
    silk(f"{j} {name}", mid, PARTS_Y - 3.6, 0.9)
    for i, n in enumerate(pins):
        silk(n, tx - i * 5.08, TERM_Y - 3.3, 0.8)

# SSR pull-downs, standing, above their terminal's SIG and GND
for tx, r in ((143.00, "R1"), (131.34, "R2"), (119.68, "R3")):
    add(r, tx - 3.81, PARTS_Y)
    ref_at(r, tx - 2.54, PARTS_Y + 2.4)

# Pressure divider and filter above J6, pull-up above J7
add("R4", 94.0, PARTS_Y)             # 10k, signal -> ADC
add("R5", 100.0, PARTS_Y)            # 20k, ADC -> GND
add("C1", 106.0, PARTS_Y)            # 100nF on ADC
add("R6", 85.0, PARTS_Y)             # 4.7k DQ pull-up
ref_at("R4", 95.3, PARTS_Y + 2.4)
ref_at("R5", 101.3, PARTS_Y + 2.4)
ref_at("C1", 108.5, PARTS_Y + 2.4)
ref_at("R6", 86.3, PARTS_Y + 2.4)

# ── board outline ────────────────────────────────────────────────────────────
rr = pcbnew.PCB_SHAPE(board)
rr.SetShape(pcbnew.SHAPE_T_RECTANGLE)
rr.SetLayer(pcbnew.Edge_Cuts)
rr.SetWidth(MM(0.15))
rr.SetStart(V(BX0, BY0)); rr.SetEnd(V(BX1, BY1))
try:
    rr.SetCornerRadius(MM(CORNER_R))
except AttributeError:
    pass
board.Add(rr)
print(f"board outline: {BX1-BX0:.1f} x {BY1-BY0:.1f} mm")

d = MH_INSET
add_mh("H1", BX0 + d, BY0 + d)
add_mh("H2", BX1 - d, BY0 + d)
add_mh("H3", BX1 - d, BY1 - d)
add_mh("H4", BX0 + d, BY1 - d)

# ── GND pour, both layers ────────────────────────────────────────────────────
for layer in (pcbnew.B_Cu, pcbnew.F_Cu):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(net_items["/GND"].GetNetCode())
    z.SetLocalClearance(MM(0.3))
    z.SetMinThickness(MM(0.25))
    set_rect(z, BX0, BY0, BX1, BY1)
    board.Add(z)

pcbnew.SaveBoard(PCB, board)
print(f"wrote {PCB}")

# ── net classes → .kicad_pro ─────────────────────────────────────────────────
try:
    pro = json.load(open(PRO))
except Exception:
    pro = {}
pro.setdefault("net_settings", {})
def netclass(name, clearance, width, via_d, via_drill, priority):
    return {"name": name, "clearance": clearance, "track_width": width,
            "via_diameter": via_d, "via_drill": via_drill,
            "diff_pair_gap": 0.25, "diff_pair_width": 0.2,
            "microvia_diameter": 0.3, "microvia_drill": 0.1,
            "wire_width": 6, "bus_width": 12, "line_style": 0,
            "pcb_color": "rgba(0,0,0,0.000)", "schematic_color": "rgba(0,0,0,0.000)",
            "priority": priority}
pro["net_settings"]["classes"] = [
    netclass("Default", 0.25, 0.3, 0.8, 0.4, 2147483647),
    netclass("Power", 0.3, 0.6, 1.0, 0.5, 1),
]
pro["net_settings"]["netclass_patterns"] = [
    {"netclass": "Power", "pattern": "/GND"},
    {"netclass": "Power", "pattern": "/+3V3"},
    {"netclass": "Power", "pattern": "/+5V"},
]
json.dump(pro, open(PRO, "w"), indent=2)
print("patched net classes into", PRO)
