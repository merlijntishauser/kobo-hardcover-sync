import pytest

from tests import PROXY


@pytest.fixture(autouse=True)
def behind_the_proxy(monkeypatch):
    """Every test runs as an installation that knows its proxy; the tests
    that are about not knowing it take the setting away again."""
    monkeypatch.setenv("KHS_TRUSTED_PROXIES", PROXY[0])


@pytest.fixture(autouse=True)
def tokens_in_the_database():
    """Local mode points the accounts module at the computer's secret store;
    no test starts with that left over from another one."""
    from kobo_hardcover_sync.server import accounts

    accounts.token_store = None
    yield
    accounts.token_store = None


@pytest.fixture
def home(tmp_path, monkeypatch):
    """The tool's own folder, and a private temp folder to check nothing is left in it."""
    monkeypatch.setenv("KHS_HOME", str(tmp_path / "state"))
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))
    return tmp_path
