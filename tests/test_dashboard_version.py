from autoft8 import __version__
from autoft8.dashboard import dashboard_state


class FakeEngine:
    def snapshot(self):
        return {"version": "stale", "armed": False}


def test_dashboard_uses_canonical_package_version():
    state = dashboard_state(FakeEngine())
    assert state["version"] == __version__
    assert state["version"] == "0.3.5"
