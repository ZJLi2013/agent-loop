from pager.protocol import Verb, parse_reply


def test_parse_ok_no_stop():
    assert parse_reply("OK\n", task_id="T12").verb is Verb.OK
    assert parse_reply("no", task_id="T12").verb is Verb.NO
    assert parse_reply("  STOP  ", task_id="T12").verb is Verb.STOP


def test_parse_do_keeps_rest_of_first_line():
    cmd = parse_reply("DO 改 topN=5 然后继续\n第二行忽略", task_id="t1")
    assert cmd.verb is Verb.DO
    assert cmd.text == "改 topN=5 然后继续"
    assert cmd.task_id == "t1"


def test_unstructured_and_ok_with_trailer_rejected():
    assert parse_reply("看起来没问题，发吧", task_id="T12") is None
    assert parse_reply("OK thanks", task_id="T12") is None
    assert parse_reply("DO", task_id="T12") is None
    assert parse_reply("OK", task_id="") is None
