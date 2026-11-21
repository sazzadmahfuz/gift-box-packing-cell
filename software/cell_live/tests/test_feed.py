"""The object belt's stop rule (control/feed.py): full set in the pick area, or a needed object at the stop line."""

from cell_live.control.feed import FeedWatch, feed_detections, still_needed
from cell_live.control.runlog import describe_detections
from cell_live.tests.control_fakes import CHOTON, item

WANT = {"card": 1, "candy": 2}


def watch(need=None, stop_y_mm=-60.0):
    return FeedWatch(WANT if need is None else need, 3, stop_y_mm, 2, CHOTON.yolo_lib.usable)


def at(kind, y_mm, **flags):
    found = item(kind, 215.0, y_mm, 400 + 2.4 * y_mm)
    found.update(flags)
    return found


def test_still_needed_counts_what_is_placed():
    assert still_needed(WANT, []) == {"card": 1, "candy": 2}
    assert still_needed(WANT, [{"type": "card"}, {"type": "candy"}]) == {"candy": 1}
    assert still_needed(WANT, [{"type": "card"}, {"type": "candy"}, {"type": "candy"}]) == {}


def test_full_set_stops_after_three_pictures_in_a_row():
    rule = watch()
    picture = [at("card", 100), at("candy", 40), at("candy", 0)]
    assert [rule.see(picture).stop for _ in range(3)] == [False, False, True]
    assert rule.see(picture).reason.startswith("the full set is in the pick area (card 1/1, candy 2/2")


def test_a_needed_object_at_the_stop_line_stops_after_two_pictures():
    rule = watch()
    assert not rule.see([at("candy", -59)]).stop  # not at the line yet
    assert not rule.see([at("candy", -61)]).stop  # first picture at the line
    decision = rule.see([at("candy", -64)])
    assert decision.stop
    assert decision.reason.startswith("candy at y = -64 mm reached the stop line (-60 mm)")
    assert "card 0/1, candy 1/2 in the pick area" in decision.reason


def test_one_missed_picture_starts_the_count_again():
    rule = watch()
    decisions = [rule.see(picture).stop for picture in ([at("card", -61)], [], [at("card", -65)], [at("card", -68)])]
    assert decisions == [False, False, False, True]


def test_an_object_the_box_does_not_need_does_not_stop_the_belt():
    rule = watch(need=still_needed(WANT, [{"type": "card"}]))
    assert not any(rule.see([at("card", -70)]).stop for _ in range(5))
    assert rule.counts == "candy 0/2 in the pick area"


def test_objects_that_are_not_usable_never_count():
    rule = watch()
    edge, outside = at("candy", -70, edge=True), at("candy", -70, reachable=False, off_belt=True)
    assert not any(rule.see([edge, outside]).stop for _ in range(5))
    assert rule.counts == "card 0/1, candy 0/2 in the pick area"


def test_without_a_stop_line_only_the_full_set_stops_the_belt():
    rule = watch(stop_y_mm=None)
    assert not any(rule.see([at("candy", -90)]).stop for _ in range(5))


def test_counts_changed_marks_the_pictures_worth_a_log_row():
    rule = watch()
    changes = [rule.see(picture).counts_changed for picture in ([], [], [at("card", 100)], [at("card", 97)], [])]
    assert changes == [True, False, True, False, True]


def test_the_log_says_why_a_card_or_candy_is_not_used():
    picture = [at("card", 300, reachable=False, off_belt=True), at("candy", 50, edge=True), at("box", 0)]
    text = describe_detections(feed_detections(picture))
    assert text == "card 0.9 (215.0, 300) +0deg NOT IN THE PICK AREA; candy 0.9 (215.0, 50) +0deg AT THE EDGE"
