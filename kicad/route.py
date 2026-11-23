#!/usr/bin/env python3
"""
Autoroute the board with freerouting, fill the zones and save it.  Run with
KiCad's Python, after generate_pcb.py; build.sh does.  Needs Java 17+ and
freerouting at $FREEROUTING, default ~/tools/freerouting-1.9.jar.

Standard file, from ~/.claude/kicad-standard/: copy it, don't edit it here.
"""
import glob
import os
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRO = glob.glob(os.path.join(HERE, "*.kicad_pro"))[0]
PCB = PRO.replace(".kicad_pro", ".kicad_pcb")
DSN = PRO.replace(".kicad_pro", ".dsn")
SES = PRO.replace(".kicad_pro", ".ses")
JAR = os.environ.get("FREEROUTING", os.path.expanduser("~/tools/freerouting-1.9.jar"))

try:
    import wx
    _APP = wx.App()
except Exception:
    pass

board = pcbnew.LoadBoard(PCB)
pcbnew.ExportSpecctraDSN(board, DSN)
subprocess.run(["java", "-jar", JAR, "-de", DSN, "-do", SES, "-mp", "30"],
               check=True, capture_output=True)

board = pcbnew.LoadBoard(PCB)
pcbnew.ImportSpecctraSES(board, SES)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
unconnected = board.GetConnectivity().GetUnconnectedCount(False)
pcbnew.SaveBoard(PCB, board)
print(f"routed {os.path.basename(PCB)}, unconnected: {unconnected}")
sys.exit(1 if unconnected else 0)
