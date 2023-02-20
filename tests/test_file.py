import cron_times.file as t


def test_parse_task():
    # minimal
    assert t.parse_task({"name": "Test", "schedule": "0 0 * * *"}) == {
        "name": "Test",
        "key": "test",
        "schedule": "0 0 * * *",
        "timezone": "UTC",
        "labels": [],
        "description": None,
    }

    # full
    everything = {
        "name": "test <tag>",
        "schedule": "0 0 * * *",
        "timezone": "America/New_York",
        "description": "sample text",
        "labels": ["Plain", {"text": "<colored>", "color": "teal"}],
    }
    assert t.parse_task(everything) == {
        "name": "test &lt;tag&gt;",
        "key": "test <tag>",
        "schedule": "0 0 * * *",
        "timezone": "America/New_York",
        "description": "<p>sample text</p>\n",
        "labels": [
            {"text": "Plain", "key": "plain", "color": None},
            {"text": "&lt;colored&gt;", "key": "<colored>", "color": "teal"},
        ],
    }

    # missing inputs
    def everything_except(f: str) -> dict:
        d = everything.copy()
        d.pop(f)
        return d

    assert t.parse_task(everything_except("name")) is None
    assert t.parse_task(everything_except("schedule")) is None


def test_is_valid_schedule():
    assert t.is_valid_schedule("0 0 * * *") is True
    assert t.is_valid_schedule("*") is False


def test_is_valid_timezone():
    assert t.is_valid_timezone("UTC") is True
    assert t.is_valid_timezone("Asia/Taipei") is True
    assert t.is_valid_timezone("CST") is False


def test_render_markdown():
    assert t.render_markdown("""sample *text* and escaped <script>""") == (
        "<p>sample <em>text</em> and escaped &lt;script&gt;</p>\n"
    )
    assert t.render_markdown(None) is None
    assert t.render_markdown("") is None
