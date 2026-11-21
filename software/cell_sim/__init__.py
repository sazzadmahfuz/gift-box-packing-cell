"""Discrete-event simulation of the packing cell (SIMULATION, assumed parameters).

Runs offline on a simulated clock. It never connects to hardware.
"""

__version__ = "0.3.0"
SIM_DEVICES_TEXT = "SimBelt A (objects), simulated belt B and S1 (Arduino Nano), MockVision"
SIMULATION_BANNER = (
    "# SIMULATION, assumed parameters; cycle: box, full set on belt A, pictures, pick and place, lid, "
    f"operator removes box; parameters: config.json (all ASSUMED); devices: SimRobot, {SIM_DEVICES_TEXT}"
)
