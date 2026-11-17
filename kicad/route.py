#!/usr/bin/env python3
"""
Autoroute rhb_water_heater.kicad_pcb with freerouting and fill the zones.
Run with KiCad's bundled python after generate_pcb.py.  Needs Java 17+ and
~/tools/freerouting-1.9.jar.
"""
import os
import subprocess
import sys

import pcbnew

PCB = "rhb_water_heater.kicad_pcb"
DSN = "rhb_water_heater.dsn"
SES = "rhb_water_heater.ses"
JAR = os.path.expanduser("~/tools/freerouting-1.9.jar")

try:
    import wx; _APP = wx.App()
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
print(f"routed {PCB}, unconnected: {unconnected}")
sys.exit(1 if unconnected else 0)
