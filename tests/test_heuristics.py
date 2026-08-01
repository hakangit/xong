from xong.heuristics import looks_vague


def test_long_title_is_vague():
    title = "the big thing about the quarterly numbers and all the details involved"
    assert looks_vague(title) is True


def test_no_verb_is_vague():
    assert looks_vague("báo cáo tháng") is True


def test_verb_not_vague():
    assert looks_vague("Send invoice to customer") is False


def test_next_action_clears_vague():
    assert looks_vague("báo cáo tháng", next_action="Mở sheet chi phí") is False
