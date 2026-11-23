#!/bin/sh
# Regenerate the board from the scripts.
#   ./build.sh             parts, schematic, board, routing, DRC, renders
#   ./build.sh --no-route  stop after DRC of the unrouted board
# A hand-laid board has no generate_*.py: this only checks and renders it.
# Standard file, from ~/.claude/kicad-standard/: copy it, don't edit it here.
set -e
cd "$(dirname "$0")"
P=$(basename *.kicad_pro .kicad_pro)
K=${KICAD:-/Applications/KiCad/KiCad.app/Contents}
CLI=$K/MacOS/kicad-cli
KPY=$K/Frameworks/Python.framework/Versions/Current/bin/python3
ROUTE=1; [ "$1" = --no-route ] && ROUTE=0

# KiCad's Python, without the wx and pcbnew chatter
kpy() {
    mkdir -p logs; rc=0
    $KPY "$@" >logs/kpy.log 2>&1 || rc=$?
    grep -v -e 'Debug: ' -e '[Ww]arning' logs/kpy.log || true
    return $rc
}

if [ -f generate_parts.py ]; then
    echo "== parts"; python3 generate_parts.py
fi

if [ -f generate_schematic.py ]; then
    echo "== schematic"
    python3 generate_schematic.py
    $CLI sch export netlist -o "$P.net" "$P.kicad_sch" >/dev/null
fi

if [ -f generate_pcb.py ]; then
    echo "== board"; kpy generate_pcb.py
    if [ $ROUTE = 1 ]; then
        echo "== route"; kpy route.py
    fi
fi

echo "== check"
$CLI sch erc --format json -o erc.json "$P.kicad_sch" >/dev/null
$CLI pcb drc --schematic-parity --format json -o drc.json "$P.kicad_pcb" >/dev/null
python3 - "$ROUTE" <<'EOF'
import collections, json, sys
routed = sys.argv[1] == "1"
failed = False
for report, keys in (("erc.json", None), ("drc.json", ("violations", "unconnected_items", "schematic_parity"))):
    d = json.load(open(report))
    items = ([v for s in d["sheets"] for v in s["violations"]] if keys is None
             else [v for k in keys for v in d.get(k, [])])
    if not routed:
        items = [v for v in items if v["type"] != "unconnected_items"]
    for (sev, typ), n in sorted(collections.Counter((v["severity"], v["type"]) for v in items).items()):
        print(f"  {report[:3]} {sev:8} {n:3} {typ}")
    failed |= any(v["severity"] == "error" for v in items)
sys.exit("errors: see erc.json, drc.json" if failed else 0)
EOF

if [ $ROUTE = 1 ]; then
    echo "== renders"
    $CLI pcb render --side top --quality high --floor -w 1600 -h 1200 -o board.png "$P.kicad_pcb" >/dev/null
    $CLI pcb export svg --mode-single --page-size-mode 2 --exclude-drawing-sheet \
        --layers F.Cu,B.Cu,F.SilkS,Edge.Cuts -o board.svg "$P.kicad_pcb" >/dev/null
fi
