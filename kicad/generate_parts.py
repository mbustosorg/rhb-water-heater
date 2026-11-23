#!/usr/bin/env python3
"""
Write rhb_water_heater.pretty/Waveshare_ESP32-S3-ETH_Socketed.kicad_mod, the
Waveshare ESP32-S3-ETH on 2 x 20 female headers.  build.sh runs this;
generate_pcb.py imports OVERHANG_AT from it.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(HERE, "rhb_water_heater.pretty")

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


if __name__ == "__main__":
    write_module_footprint(os.path.join(LOCAL, "Waveshare_ESP32-S3-ETH_Socketed.kicad_mod"))
