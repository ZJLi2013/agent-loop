from pager.protocol import Verb, parse_reply, parse_subject, render_page


def test_render_subject_carries_task_id():
    page = render_page("T12", "需要批准：跑 zhihu_pipeline --days 7")
    assert page.subject == "[agent T12] 需要批准：跑 zhihu_pipeline --days 7"
    assert parse_subject(page.subject) == (
        "T12",
        "需要批准：跑 zhihu_pipeline --days 7",
    )
    assert parse_subject("Re: " + page.subject)[0] == "T12"


def test_parse_ok_no_stop():
    assert parse_reply("OK\n", task_id="T12").verb is Verb.OK
    assert parse_reply("no", task_id="T12").verb is Verb.NO
    assert parse_reply("  STOP  ", task_id="T12").verb is Verb.STOP


def test_parse_do_keeps_rest_of_first_line():
    cmd = parse_reply("DO 改 topN=5 然后继续\n第二行忽略", task_id="t1")
    assert cmd.verb is Verb.DO
    assert cmd.text == "改 topN=5 然后继续"
    assert cmd.task_id == "t1"


def test_quoted_history_after_command_is_dropped():
    body = "OK\n\n> [agent T12] 需要批准\n> 选项：OK / NO\n"
    assert parse_reply(body, task_id="T12").verb is Verb.OK


def test_quote_only_mail_is_ignored():
    body = "> On Tue, agent wrote:\n> please reply OK\n"
    assert parse_reply(body, task_id="T12") is None


def test_unstructured_and_ok_with_trailer_rejected():
    assert parse_reply("看起来没问题，发吧", task_id="T12") is None
    assert parse_reply("OK thanks", task_id="T12") is None
    assert parse_reply("DO", task_id="T12") is None
    assert parse_reply("OK", task_id="") is None
