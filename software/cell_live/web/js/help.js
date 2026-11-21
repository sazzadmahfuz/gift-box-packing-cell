// Help screen: wiring summary (numbers read from /api/config), start-up order, what each status
// means, and what to do if something goes wrong.
import { getJSON } from "./api.js";
import { STATES, badge, h, text } from "./ui.js";

const MEANINGS = {
  OK: "The last check saw the component working.",
  WARN: "It answers, but something needs attention (for example a robot alarm).",
  FAIL: "The last check failed. The detail says why.",
  UNKNOWN: "Not checked yet, or the answer could not be read.",
  NOT_OBSERVABLE: "This PC cannot see it (not configured, or not connected to anything this PC can read).",
};

const WHAT_IF = [
  ["Robot is held by another program", "Close DobotStudio Pro and Choton's scripts. Only one program may hold the robot ports."],
  ["Robot unreachable", "Cable in LAN1, this PC on 192.168.1.x (not .6), robot powered. Then Check."],
  ["Camera NOT OBSERVABLE", "Open Settings and press Scan cameras. Use the right index, add the source, press Save. Then open Vision and press Start camera."],
  ["Object belt does not move although DO3 is at its run level", "The step pulses come from the box belt's UNO. Check that the UNO is powered (USB-C supply) and its sketch runs: the box belt moves when no box is at the sensor."],
  ["Vision model FAIL", "Install the package shown in the tile (python -m pip install ultralytics), then restart the backend."],
  ["PAUSED: no box", "Put an open, empty box on the box belt at the box slot (red mark on Vision), then Resume. A box with items in it is not seen as an open box: take it away first. While a run is paused the box belt may stand still: on 17 Nov it did not bring a box during a pause (the pause switches the belt enable DO16 off; whether DO16 also holds the box belt is still to confirm), so move the box by hand."],
  ["PAUSED: box not under the box slot", "The robot drops every item at the taught box slot (red mark on Vision). Move the open box until the mark is in its middle (the text says how far), keeping the box at the sensor so the box belt stays stopped. Resume."],
  ["Placing the objects", "Lay the card and the candies on the object belt, a few centimetres apart: touching items are seen as one. Either way round is fine: the robot turns each item into the direction of the box. An item is not counted while it touches the left or right end of the picture, or lies outside the pick area (the blue rectangle on Vision)."],
  ["PAUSED: not enough objects", "Put 1 card and 2 candies on the object belt, apart (see Placing the objects). Vision shows why an item is not counted (EDGE, out of reach, outside the pick area). Resume (the belt starts again)."],
  ["PAUSED: object missing", "An item moved or fell. Place it in the pick area, Resume (new pictures first), or Skip box."],
  ["PAUSED: lid not found or out of reach", "Lay the lid flat against the box on its downstream side (left of the box on Vision), the same way round as the box. The bottom of the picture cuts the far end of the box and of the lid a little: the run works out the lid's middle from its size, and the Lid line on Run and Vision says how many millimetres are outside. On the right of the box the lid's middle is about 390 mm from the robot: out of reach. A lid seen at the box slot is the filled box itself and is never picked. Resume, or Skip box."],
  ["An item lies crosswise in the box", "The robot turns each item so its long side lies along the open box; each pick row in the log says turn N deg. The direction is measured when the EMPTY box has stopped. If the log says the direction of the box is not known, start the box empty."],
  ["PAUSED: box did not leave", "Take the closed box off the box belt by hand. The belt brings the next box and stops at the sensor. Resume."],
  ["PAUSED: move refused", "The robot refused a move (outside its work area?). Check the Overview and the alarm text. Resume or Abort."],
  ["Object belt does not stop", "It stops when the set is in the pick area or a needed item reaches the red stop line on Vision. If an item there is not counted (EDGE, outside the pick area), see Placing the objects. Press Stop object belt (Run screen) or SOFTWARE STOP. If it still runs, the DO3 level is backwards: check dobot.belt_on_value in Settings (17 Nov: 0 runs the belt) and Choton's robot.belt_on."],
  ["Arm refused: the arm cannot move straight home", "Every run begins with a straight move home. From some places (17 Nov: the middle calibration mark) that line needs J1 beyond its range of 85 degrees and the robot would stop with an alarm. Move the arm first: stop the console, run Choton's 15_robot_setup.py, press x and click on the box belt where the box stands (the cup goes above it), press q, start the console again."],
  ["Checking a run afterwards", "Logs shows every row of the run. The camera picture of each decision (box, belt, each look, the closed box) is saved in testing/live_runs, in the folder named after the run, and the log row names the file."],
  ["FAULT", "Press the physical emergency stop if anything is unsafe. Read the fault text, Clear alarm, then Abort. All Overview tiles must be OK before the next Arm."],
  ["Backend connection lost (red banner, grey tiles)", "The page shows old data. Start python -m cell_live again in the software folder, then reload the page."],
];

function wiring(values) {
  const value = (name) => text(values[name]);
  const output = (name) => (values[name] === null || values[name] === undefined ? "not set yet (CONFIRM)" : `DO${values[name]}`);
  return h("table", { class: "data" }, h("tbody", {},
    h("tr", {}, h("th", {}, "Robot"), h("td", {}, `Dobot M1 Pro at ${value("dobot.ip")}: dashboard port ${value("dobot.dashboard_port")}, moves ${value("dobot.move_port")}, feedback ${value("dobot.feedback_port")}`)),
    h("tr", {}, h("th", {}, "Object belt"), h("td", {}, `Cards and candies, belt ${value("belts.object_belt_serial")}. Its driver gets the step pulses from the box belt's UNO. The robot sets start and stop with ${output("dobot.belt_do")} (level ${value("dobot.belt_on_value")} runs it), direction with ${output("dobot.belt_dir_do")} and enable with ${output("dobot.belt_enable_do")}.`)),
    h("tr", {}, h("th", {}, "Box belt"), h("td", {}, `Boxes and lids, belt ${value("belts.box_belt_serial")}. Run by an ${value("arduino.board")} with the E18-D80NK sensor (Rashmika's sketch): it runs while the sensor is clear, stops 50 ms after the sensor sees a box and starts again 50 ms after the box is taken away. The UNO sends the step pulses for both belts. Rashmika calls it belt A. The camera confirms the box.`)),
    h("tr", {}, h("th", {}, "Box moves on"), h("td", {}, `belts.box_restart: ${values["belts.box_restart"] ?? "not set yet (CONFIRM)"}. Operator: a person takes the closed box away.`)),
    h("tr", {}, h("th", {}, "Vacuum"), h("td", {}, `Suction DO${value("dobot.vacuum_do")}, blow-off DO${value("dobot.blow_do")}`)),
    h("tr", {}, h("th", {}, "Camera"), h("td", {}, `USB camera index ${value("camera.index")}, ${value("camera.width_px")} x ${value("camera.height_px")}`)),
    h("tr", {}, h("th", {}, "Robot reach"), h("td", {}, `${value("control.reach_min_mm")} to ${value("control.reach_max_mm")} mm from the robot origin`))));
}

export function render(root) {
  const wiringHost = h("div", {}, h("p", { class: "muted" }, "Loading the wiring from the config…"));
  root.append(h("div", { class: "help" },
    h("div", { class: "screen-head" }, h("h1", {}, "Help")),
    h("div", { class: "split even" },
      h("section", { class: "panel" },
        h("h2", {}, "Wiring (from live_config.json)"), wiringHost,
        h("h2", {}, "Start-up order (operator: Sazzad)"),
        h("ol", {},
          h("li", {}, "Laptop Ethernet on 192.168.1.x (not .6), cable in the robot's LAN1."),
          h("li", {}, "Close DobotStudio Pro and Choton's scripts: only one program may hold the robot."),
          h("li", {}, "Robot powered. Physical emergency stop released and in reach of the operator."),
          h("li", {}, "In the software folder: python -m cell_live. Operator window: http://127.0.0.1:8765/ on the laptop screen."),
          h("li", {}, "Projector window: http://127.0.0.1:8765/?viewer=1#/show (Viewer mode: Overview and camera side by side)."),
          h("li", {}, "Overview: every hardware lamp OK (the box belt controller may be NOT OBSERVABLE: it is not connected to this PC)."),
          h("li", {}, "Settings: lab values filled in, each with its status and source."),
          h("li", {}, "Run: hand on the physical emergency stop, tick the box, Arm, then Start within 60 s."))),
      h("section", { class: "panel" },
        h("h2", {}, "What each status means"),
        h("ul", {}, ...Object.keys(STATES).map((state) => h("li", {}, badge(state), " ", MEANINGS[state]))),
        h("p", {}, badge("OK", true), " grey: the data is old (more than two check intervals) or the backend connection is lost."),
        h("p", {}, h("span", { class: "tag" }, "file"), " a file on this PC (calibration, model), not a device. ",
          h("span", { class: "tag" }, "hardware"), " a device of the cell."),
        h("h2", {}, "Stops"),
        h("p", {}, h("strong", {}, "The physical emergency stop comes first."), " The SOFTWARE STOP switches the belt, suction and blow-off off and sends EmergencyStop to the robot. It is a software stop only and stays on screen in Viewer mode."),
        h("h2", {}, "What to do if"),
        h("table", { class: "data" }, h("tbody", {}, ...WHAT_IF.map(([problem, action]) => h("tr", {}, h("th", {}, problem), h("td", {}, action)))))))));

  getJSON("/api/config").then((config) => {
    const values = Object.fromEntries(config.entries.map((entry) => [`${entry.section}.${entry.key}`, entry.value]));
    wiringHost.replaceChildren(wiring(values));
  }).catch((error) => wiringHost.replaceChildren(h("p", { class: "result-fail" }, `Config not available: ${error.message}`)));
}
