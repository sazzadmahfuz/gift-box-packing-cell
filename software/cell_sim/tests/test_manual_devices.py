import threading

from cell_sim.drivers.manual_devices import ManualBelt, ManualSensor


def test_manual_belt_waits_for_the_operator_on_start_and_stop():
    prompts, messages = [], []
    belt = ManualBelt("A", ask=lambda text: prompts.append(text) or "", say=messages.append)
    belt.stop()  # not running: nothing to ask
    assert prompts == []
    belt.start()
    assert belt.is_running()
    belt.stop()
    assert not belt.is_running()
    assert len(prompts) == 2
    assert "Start belt A" in messages[0] and "Stop belt A" in messages[1]


def test_manual_sensor_toggles_on_each_enter_press():
    presses = threading.Semaphore(0)

    def ask(_prompt):
        presses.acquire()
        return ""

    sensor = ManualSensor(ask=ask, say=lambda _text: None)
    sensor.start_listening()
    assert not sensor.is_active()

    presses.release()
    assert sensor.wait_for_change(timeout_s=2.0)
    assert sensor.is_active()

    presses.release()
    assert sensor.wait_for_change(timeout_s=2.0)
    assert not sensor.is_active()


def test_manual_sensor_stops_listening_at_end_of_input():
    def ask(_prompt):
        raise EOFError

    sensor = ManualSensor(ask=ask, say=lambda _text: None)
    sensor.start_listening()
    sensor._thread.join(timeout=2.0)
    assert not sensor._thread.is_alive()
    assert not sensor.is_active()
