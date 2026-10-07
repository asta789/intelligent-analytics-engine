from types import SimpleNamespace

from app.planner import Planner


class FakeClient:
    def __init__(self):
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if len(self.calls) == 1:
            error = RuntimeError("temporary failure")
            error.status_code = 503
            raise error
        return SimpleNamespace(
            text='{"sql":"SELECT 1","interpretation":"Test query","confidence":0.9,"assumptions":[]}'
        )


def test_retry_then_success(monkeypatch):
    catalog = SimpleNamespace(prompt_context=lambda: "TABLE sales_data (id INTEGER)")
    planner = Planner(catalog)
    planner.client = FakeClient()
    monkeypatch.setattr("app.planner.time.sleep", lambda _: None)

    result = planner.plan("test")

    assert result.sql == "SELECT 1"
    assert planner.client.calls == ["gemini-3.8-flash", "gemini-3.8-flash"]
