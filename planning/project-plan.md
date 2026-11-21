# Team Project Plan

Fill in and discuss this plan during the Week 1 lecture. Update it each week.

## 0. Set Up Your Engineering Notebook

- Set up your GitHub account, create your engineering notebook and merge it into the main branch.

## 1. Review the Applied Project I Plan

**Previous plan / report:**

| Review Question | Team Answer |
|---|---|
| What problem does the system solve? | The system automates the assembly of a Christmas gift box containing two different types of candy and a Christmas card. |
| What is already working, and what is untested? | The Dobot Nova 2 robot arm and conveyor belt have been tested. The other equipment and technologies have not yet been tested. |
| What is our minimum working demo for Week 4? | The system should assemble a Christmas gift box containing two different types of candy and a Christmas card while the conveyor belt remains stationary. |
| What is our final goal for Week 8? | The system should perform the same packaging task while the conveyor belt is moving. |
| What is optional or outside our scope? | The Beckhoff machine vision system and the Intel RealSense D435i depth camera are optional components and may be considered if time and resources permit. |


## 2. Resources to Check

| Equipment / Software / Material | Availability or Requirement | Responsible Person | Needed By |
|---|---|---|---|
| Conveyor belt | Tested; verify operational condition | Rashmika | Week 1 |
| Dobot Nova 2 robot arm | Tested; verify operational condition | Rashmika | Week 1 |
| Beckhoff machine vision system | Testing required | Rashmika | TBD |
| RGB camera | Testing required | Choton / Sazaad | Week 1 |
| Delta robot | Testing required | Rashmika | Week 1 |
| Raspberry Pi 4 / Raspberry Pi 5 | Check availability and suitability | Team | TBD |
| NVIDIA Jetson Orin NX | Evaluate whether required | Team | TBD |
| RPLIDAR 2D sensor | Confirm availability and use case | TBD | TBD |
| Intel RealSense D435i depth camera | Confirm availability and use case | TBD | TBD |
| Machine Vision | Evaluate for robot simulation | Sazaad / Choton | Week 1 |
| Visual Components/ Gazebo | Evaluate for production-line simulation | Team | TBD |
| NVIDIA Isaac Sim | Evaluate for robotics simulation | Team | TBD |
| Christmas cards | Confirm material availability | Team | Week 4 |
| Two types of candy | Confirm material availability | Team | Week 4 |
| Gift boxes | Confirm material availability | Team | Week 4 |

## 3. Team Working Agreement

- **Team discussion channel / Teams group link:** HAMK Microsoft Teams group for the project [Applied Robotics Project 2](https://teams.microsoft.com/l/team/19%3AB5oapZnSdt_olmnNSBXdWJHzL5BGhcgnyBrMMVjUom81%40thread.tacv2/conversations?groupId=0fc618f7-cfe4-458b-9cd5-eee51722ace6&tenantId=fbd2f045-b34c-4673-9534-8f2374355cec).
- **Team weekly meeting — day, time and location:** To be agreed by the team during the Week 1 lecture. Location: HAMK robotics laboratory or Microsoft Teams.
- **Daily stand-up meeting on project workdays — time and location/channel:** Brief meeting at the beginning of each project workday in the laboratory or via Microsoft Teams.

  Each team member should report:
  - What have I completed?
  - What will I work on next?
  - What is blocking me, or what help do I need?

- **Engineering notebook:** Each team member must update their engineering notebook daily, including completed work, code changes, test results, problems, photographs, and evidence.
- **Weekly review:** During each lecture, the team will demonstrate progress, review test evidence and engineering notebooks, discuss problems, and agree on the next actions.
- **Absence or missed deadline:** The team member must notify the team through Microsoft Teams as soon as possible, explain the issue, and update their task status. The team will agree on a backup or revised deadline.



## 4. Required Weekly Deliverables

Each numbered tag identifies one required deliverable. Use these tags in the student task table in Section 5 to show which deliverable each task contributes to. One deliverable may require several tasks; one task may contribute to several deliverables.

| Deliverable tag | Week | Main focus | Required deliverable |
|---|---|---|---|
| D1.1 | 1 | Review and plan | Previous-plan review with links to existing files and a list of working, untested and faulty functions. |
| D1.2 | 1 | Review and plan | Agreed scope: Week 4 minimum demo, Week 8 final goal and scope exclusions. |
| D1.3 | 1 | Review and plan | Resource availability check covering equipment, software and materials. |
| D1.4 | 1 | Review and plan | Initial risk register with mitigation, fallbacks and owners, including safety and laboratory access requirements to confirm with the teacher. |
| D1.5 | 1 | Review and plan | System/interface diagram and signal/data interface table. |
| D1.6 | 1 | Review and plan | Proposed measurable acceptance criteria and test conditions for the Week 4 and Week 8 demos. |
| D1.7 | 1 | Review and plan | Detailed task plan for Weeks 1-4 with named leads, partners, reviewers and actual planned work dates. |
| D2.1 | 2 | Test modules | Saved hardware, software and mechanical module files with setup instructions. |
| D2.2 | 2 | Test modules | Module test records showing conditions, expected results, actual results and open faults. |
| D2.3 | 2 | Test modules | Runnable normal-operation simulation with run instructions and recorded cycle results. |
| D2.4 | 2 | Test modules | Updated interface definitions reflecting the tested modules. |
| D3.1 | 3 | Integrate | Saved integrated hardware workflow with demonstration evidence and sequence test results. |
| D3.2 | 3 | Integrate | Simulated fault scenarios with expected and observed system responses. |
| D3.3 | 3 | Integrate | Issue list with correction owners and deadlines. |
| D4.1 | 4 | Demo V1 | V1 demonstration evidence from hardware and simulation. |
| D4.2 | 4 | Demo V1 | Baseline performance measurements and test records under stated conditions. |
| D4.3 | 4 | Demo V1 | Clearly labelled V1 snapshot of editable project files. |
| D4.4 | 4 | Demo V1 | Prioritised improvement list linked to V1 findings and a revised task plan for Weeks 5-8. |
| D5.1 | 5 | Improve | Updated project files showing implemented improvements linked to the selected V1 findings. |
| D5.2 | 5 | Improve | Initial test results for each implemented improvement. |
| D5.3 | 5 | Improve | Updated task plan, status records and project documentation. |
| D6.1 | 6 | Integrate V2 | Integrated, runnable V2 hardware and simulation project files. |
| D6.2 | 6 | Integrate V2 | Results of repeated tests for functions affected by the changes. |
| D6.3 | 6 | Integrate V2 | Clearly labelled V2 snapshot and remaining-defect list. |
| D6.4 | 6 | Integrate V2 | Recorded feature-freeze decision stating what is included and what is deferred. |
| D7.1 | 7 | Evaluate and rehearse | Acceptance and fault-test records with a V1/V2 performance comparison. |
| D7.2 | 7 | Evaluate and rehearse | User feedback and a list of remaining corrections with named owners. |
| D7.3 | 7 | Evaluate and rehearse | Draft handover package: setup, operation and troubleshooting instructions plus an editable file index. |
| D7.4 | 7 | Evaluate and rehearse | Demo script and rehearsal record with assigned corrections. |
| D8.1 | 8 | Public open demo and handover | Final hardware and simulation demonstration evidence. |
| D8.2 | 8 | Public open demo and handover | Final acceptance results and known limitations. |
| D8.3 | 8 | Public open demo and handover | Complete handover package with instructions, editable project files and setup/run information. |
| D8.4 | 8 | Public open demo and handover | Completed individual engineering notebooks and individual contribution summaries. |


## 5. Weekly Tasks

| Task ID / week | Deliverable tag(s) | Student-defined task and output | Student responsible for the task (lead) | Partner | Reviewer | Planned workdays per student | Due date | Estimated person-hours | Acceptance criterion | Risk or dependency / response | Status / evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 / W1 | D1.1, D1.2 | Review the previous project plan, confirm the Christmas gift-box packaging requirements, and define the Week 4 and Week 8 goals. Output: updated project scope and requirements. | Rashmika | Choton / Sazaad | Teacher | W1: Days 1–2 | End of W1 | 4 | The team agrees on the minimum demo, final goal, and project exclusions. | Unclear requirements may cause delays; confirm the scope with the teacher. | Done |
| T02 / W1 | D1.3, D1.4 | Check the availability and condition of the Nova 2 robot, conveyor belt, gripper, sensors, camera, PLC, and required software. Output: resource checklist and initial risk register. | Rashmika | Choton / Sazaad | Teacher | W1: Days 1–3 | End of W1 | 4 | Equipment is classified as available, tested, untested, faulty, or unavailable. Owners are assigned to outstanding checks. | Missing equipment may delay integration; identify alternatives early. | Done |
| T03 / W1 | D1.5, D1.6, D1.7 | Design the system architecture, define robot/conveyor interfaces, propose acceptance criteria, and prepare the task schedule for Weeks 1–4. Output: block diagram, interface table, and task plan. | Sazzad | Choton / Rashmika | Teacher | W1: Days 3–5 | End of W1 | 6 | The diagram shows the robot, conveyor, controller, sensors, operator, and data/signal connections. Measurable demo criteria are documented. | Interface uncertainty may cause integration problems; verify available communication methods and hardware connections. | IN Progress (Remote control setup) |
| T04 / W2 | D2.1, D2.2 | Test the Nova 2 robot arm, verify safe movement, and develop a repeatable pick-and-place sequence. Output: saved robot program and test log. | Rashmika | Choton | Sazaad | W2: Days 1–3 | End of W2 | 8 | The robot completes five consecutive stationary pick-and-place cycles without dropping an object, under agreed safe test conditions. | Robot errors or communication problems; check robot status, connection, gripper, and motion limits. | Robot tested; sequence validation pending |
| T05 / W2 | D2.1, D2.2, D2.4 | Test the conveyor belt, identify its control interface, and verify sensor operation if available. Output: conveyor test program and interface documentation. | Sazaad | Rashmika | Choton | W2: Days 2–4 | End of W2 | 8 | The conveyor starts and stops reliably under the intended control method, and available sensor signals are documented. | Missing controller or sensor interface; use manual testing or a suitable simulated signal for preliminary software development. | Conveyor tested; interface validation pending |
| T06 / W3 | D2.2, D2.3, D2.4 | Investigate machine vision and simulation options. Test the RGB camera and evaluate Gazebo, Visual Components, or NVIDIA Isaac Sim according to availability. Output: feasibility report and, if practical, a basic simulation. | Choton / Sazaad | Rashmika | Teacher | W3: Days 1–4 | End of W3 | 10 | Camera availability and basic image capture are verified, or limitations are documented. At least one simulation option is evaluated with setup instructions. | Installation or hardware compatibility problems; prioritise a basic camera test and the simplest feasible simulation. | Not tested |
| T07 / W3 | D3.1, D3.2, D3.3 | Integrate the robot, conveyor, gripper, and required control sequence. Test normal operation and selected fault scenarios. Output: integrated workflow, test records, and issue list. | Rashmika | Choton / Sazaad | Teacher | W3: Days 3–5 | End of W3 | 12 | The robot and conveyor can be operated in a coordinated stationary-conveyor workflow, with faults and limitations documented. | Timing or communication failures; test each module independently before integration. | Planned |
| T08 / W4 | D4.1, D4.2, D4.3, D4.4 | Complete and demonstrate V1: pack two types of candy and one Christmas card into a gift box while the conveyor is stationary. Record performance and identify improvements. Output: demonstration evidence, test results, and V1 snapshot. | Rashmika | Choton / Sazaad | Teacher | W4: Days 1–5 | End of W4 | 12 | Complete five consecutive packaging cycles without dropping items or causing an unsafe condition, under agreed test conditions. Record cycle results and known limitations. | Gripper, positioning, or sequencing problems; use predefined positions and simplify the sequence if needed. | Planned |
| T09 / W5 | D5.1, D5.2, D5.3 | Improve the V1 workflow based on recorded problems. Refine robot positions, gripper operation, conveyor control, and software reliability. Output: improved files and test results. | Rashmika | Choton / Sazaad | Teacher | W5: Days 1–5 | End of W5 | 12 | Selected V1 issues have documented corrections, and the modified functions pass their initial tests. | Too many simultaneous changes may introduce new faults; implement and test improvements incrementally. | Planned |
| T10 / W6 | D6.1, D6.2, D6.3, D6.4 | Integrate and test V2, including conveyor movement and coordinated robot operation. Evaluate machine vision only if it is feasible and does not jeopardise the main goal. Output: integrated V2, repeated test records, and feature-freeze decision. | Rashmika | Choton / Sazaad | Teacher | W6: Days 1–5 | End of W6 | 14 | The moving-conveyor workflow runs under agreed conditions, or remaining limitations are documented with a decision on deferred features. | Conveyor timing or object-position errors; use sensors or a validated timing strategy and retain a stationary-conveyor fallback. | Planned |
| T11 / W7 | D7.1, D7.2, D7.3, D7.4 | Evaluate V2, repeat acceptance and fault tests, compare results with V1, prepare the handover documents, and rehearse the final demonstration. Output: comparison report, instructions, and rehearsal record. | Rashmika | Choton / Sazaad | Teacher | W7: Days 1–5 | End of W7 | 12 | Acceptance tests are recorded, faults have assigned owners, and another team member can follow the setup and operating instructions. | Last-minute faults may affect the demo; freeze features and prioritise critical fixes. | Planned |
| T12 / W8 | D8.1, D8.2, D8.3, D8.4 | Perform the final public demonstration, verify acceptance criteria, document known limitations, and submit editable project files and individual engineering notebooks. Output: final demonstration and handover package. | Rashmika | Choton / Sazaad | Teacher | W8: Days 1–5 | End of W8 | 10 | The team demonstrates the final workflow, reports actual test results, and delivers the agreed project files, operating instructions, and individual contribution summaries. | Unexpected demonstration failure; prepare a tested backup sequence and retain V1 files. | Planned |


Example criterion: "The robot completes five consecutive pick-and-place cycles without dropping an object." Agree on test conditions with the teacher.

## 6. Project Risks and Mitigation

What could prevent us from reaching the project goal? Review risks each week.

| Risk | Impact on the goal / schedule | Mitigation: reduce the risk now | Fallback: what we do if it happens | Owner | Status |
|---|---|---|---|---|---|
| A key sensor breaks or replacement takes time. | Integration or testing is delayed. | Test sensors early; check spare availability and delivery times. | Use a compatible spare or simulate inputs for software work while waiting. | Rashmika | Open |
| A team member is sick or unavailable. | Their tasks may be delayed. | Share code and notes daily; assign a backup for each main responsibility. | Reassign priority tasks and adjust the weekly plan. | All team members | Open |
| Nova 2 communication or motion-control errors occur. | The robot may not complete the packaging sequence reliably. | Test communication, robot status, motion commands, and individual movements before integration. | Use a previously tested robot program and investigate the error separately. | Rashmika | Open |
| Conveyor speed or timing is inconsistent. | Items may arrive at the wrong position, causing failed picks. | Test conveyor start/stop control and determine how item position will be detected. | Use the stationary-conveyor workflow or a slower, controlled conveyor sequence. | Rashmika | Open |
| Gripper cannot reliably pick up candy or the Christmas card. | Items may be dropped or incorrectly positioned in the gift box. | Test gripping with the actual objects and adjust the gripper, positions, and approach angles. | Simplify the packaging sequence or use a suitable available gripper. | Rashmika | Open |
| Machine vision hardware or software is unavailable or difficult to configure. | Object detection and sorting may be delayed. | Check camera availability and test image capture early. Keep machine vision outside the minimum demo until validated. | Use predefined robot positions and manually arranged objects. | Choton / Sazaad | Open |
| Raspberry Pi or NVIDIA Jetson integration takes too long. | Additional processing or vision functions may not be completed. | Confirm whether an additional computer is necessary before developing the integration. | Use the available control computer and postpone optional processing features. | Choton / Sazaad | Open |
| Simulation software is incompatible or difficult to configure. | Simulation deliverables may be delayed. | Evaluate the available simulation software early and choose one feasible option. | Document the limitation and prioritise hardware testing and a simpler runnable simulation. | Sazaad / Choton | Open |
| Robot, conveyor, and sensors use incompatible interfaces. | The integrated workflow may fail. | Document communication protocols, input/output signals, and control responsibilities in Week 1. | Test modules independently and use an approved alternative interface or control sequence. | Rashmika | Open |
| Safety requirements or laboratory access restrict testing. | Hardware testing or demonstration may be delayed. | Confirm laboratory access, supervision, emergency-stop arrangements, and approved operating procedures with the teacher. | Continue with offline software development and simulation until testing is authorised. | All team members | To be confirmed |
| Christmas cards, candy, or gift boxes are unavailable. | The packaging demonstration cannot be completed as planned. | Confirm materials and dimensions early and prepare suitable test objects. | Use representative test objects until the actual packaging materials are available. | Choton / Sazaad | Open |
| Integration takes longer than expected. | The Week 4 or Week 8 milestone may be missed. | Prioritise the minimum packaging sequence and test one function at a time. | Defer machine vision, depth sensing, and advanced simulation features. | All team members | Open |
| Project files or test evidence are lost. | Rework is required and individual contributions may be difficult to verify. | Commit code and documentation regularly, keep backups, and update engineering notebooks daily. | Restore the latest repository version and reconstruct missing test records where possible. | All team members | Open |

### Risk Review Schedule

- **Week 1:** Identify initial risks, verify resources, and confirm laboratory safety requirements.
- **Week 2:** Review robot, conveyor, gripper, and sensor test results.
- **Week 3:** Review integration, interface, and simulation risks.
- **Week 4:** Record V1 failures and pr Do you know how too much youareusing MitaskIalwaysusing bitter we see not said when you check the dont isrange andrich because if we have three uhcame there need to consider the distance between this and thisioritise improvements.
- **Week 5:** Review improvement results and remaining technical problems.
- **Week 6:** Confirm V2 functionality and decide which optional features must be deferred.
- **Week 7:** Review acceptance tests, final demonstration risks, and handover readiness.
- **Week 8:** Record final test results, unresolved issues, and known limitations.

### Final Project Priorities

1. **Priority 1:** Reliable Nova 2 pick-and-place operation.
2. **Priority 2:** Reliable conveyor control and coordination with the robot.
3. **Priority 3:** Complete the Week 4 stationary-conveyor packaging demonstration.
4. **Priority 4:** Achieve the Week 8 moving-conveyor packaging demonstration.
5. **Priority 5:** Add machine vision, depth sensing, or advanced simulation only if the core project remains on schedule.
