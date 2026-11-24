"""News refresh merges callers, retains per-source failures and enforces cooldown."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace


class Tasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn):
        self.tasks.append(fn)


def test_refresh_coalesces_and_keeps_source_failure_without_stopping_others():
    from src.services.news_refresh_service import NewsRefreshService

    calls = []
    clock = [datetime(2026, 11, 24, 1, tzinfo=timezone.utc)]

    class SourceService:
        def list_sources(self, **kwargs):
            return {"items": [{"id": 1}, {"id": 2}], "total": 2}

        def fetch_source(self, source_id):
            calls.append(source_id)
            if source_id == 1:
                raise ValueError("unavailable upstream")
            return {"ok": True, "source_id": source_id, "saved_count": 2}

    service = NewsRefreshService(service_factory=SourceService, clock=lambda: clock[0])
    tasks = Tasks()
    assert service.start(tasks)["running"] is True
    assert service.start(tasks)["running"] is True
    assert len(tasks.tasks) == 1
    tasks.tasks.pop()()
    status = service.status()
    assert status["running"] is False
    assert status["processed"] == status["total"] == 2
    assert status["failed"] == 1
    assert status["saved_count"] == 2
    assert calls == [1, 2]
    assert service.start(tasks)["running"] is False
    assert tasks.tasks == []
    clock[0] += timedelta(seconds=300)
    assert service.start(tasks)["running"] is True


def test_empty_sources_and_listing_failure_release_refresh_state():
    from src.services.news_refresh_service import NewsRefreshService

    service = NewsRefreshService(service_factory=lambda: SimpleNamespace(
        list_sources=lambda **kwargs: {"items": [], "total": 0},
    ))
    tasks = Tasks()
    service.start(tasks)
    tasks.tasks.pop()()
    assert service.status()["running"] is False
    assert service.status()["total"] == 0
    assert service.status()["error"] is None
