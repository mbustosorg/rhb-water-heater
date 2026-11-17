#!/bin/sh
# Regenerate the schematic and the unrouted board, and run DRC on the
# placement.  For trying a layout change; README.md has the full sequence.
set -e
cd "$(dirname "$0")"
K=/Applications/KiCad/KiCad.app/Contents
KP=$K/Frameworks/Python.framework/Versions/Current/bin/python3
python3 generate_schematic.py >/dev/null
$K/MacOS/kicad-cli sch export netlist -o rhb_water_heater.net rhb_water_heater.kicad_sch >/dev/null
$KP generate_pcb.py 2>&1 | grep -v -i warning
$K/MacOS/kicad-cli pcb drc -o drc.rpt rhb_water_heater.kicad_pcb >/dev/null || true
grep -E "^\[" drc.rpt | sort | uniq -c
