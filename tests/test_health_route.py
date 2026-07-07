import json
from types import SimpleNamespace

from backend.app.api.routes.health import readiness_check


class _ReadinessDBStub:
    def execute(self, statement):
        return None


def test_readiness_check_reports_ready(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.routes.health.get_ollama_service",
        lambda: SimpleNamespace(is_model_ready=lambda: True),
    )

    response = readiness_check(db=_ReadinessDBStub())

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "ready",
        "checks": {
            "database": True,
            "ollama": True,
            "ollama_model": True,
        },
    }


def test_readiness_check_reports_not_ready_when_model_missing(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.routes.health.get_ollama_service",
        lambda: SimpleNamespace(is_model_ready=lambda: False),
    )

    response = readiness_check(db=_ReadinessDBStub())

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "not_ready",
        "checks": {
            "database": True,
            "ollama": False,
            "ollama_model": False,
        },
    }
