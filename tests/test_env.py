from kobo_hardcover_sync.env import env


def test_settings_are_read_under_one_name(monkeypatch):
    monkeypatch.delenv("KHS_DATA", raising=False)
    assert env("DATA", "/default") == "/default" and env("DATA") is None
    monkeypatch.setenv("KOBO_SYNC_DATA", "/old")  # the name from before the project was renamed: no longer read
    assert env("DATA", "/default") == "/default"
    monkeypatch.setenv("KHS_DATA", "/new")
    assert env("DATA", "/default") == "/new"
