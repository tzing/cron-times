import cron_times.timezone as t


def test_list_timezones():
    out = t.list_timezones()
    assert isinstance(out, list)
    assert all(isinstance(d, dict) for d in out)
