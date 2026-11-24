"""Per-application, coalesced news refresh using existing source protections."""
from datetime import datetime, timedelta, timezone
import threading

from src.services.intelligence_service import IntelligenceService


class NewsRefreshService:
    def __init__(self, service_factory=IntelligenceService, clock=None):
        self._factory = service_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._next = None
        self._state = dict(running=False, processed=0, total=0, failed=0, saved_count=0,
                           started_at=None, finished_at=None, next_allowed_at=None, error=None)

    def status(self):
        with self._lock:
            return dict(self._state)

    def start(self, background_tasks):
        with self._lock:
            now = self._clock()
            if self._state['running'] or self._next is not None and now < self._next:
                return dict(self._state)
            # Capture this request's repository/config before accepting the job.
            service = self._factory()
            self._next = now + timedelta(seconds=300)
            self._state = dict(running=True, processed=0, total=0, failed=0, saved_count=0,
                               started_at=now.isoformat(), finished_at=None,
                               next_allowed_at=self._next.isoformat(), error=None)
            try:
                background_tasks.add_task(lambda: self._run(service))
            except Exception:
                self._state['running'] = False
                self._next = None
                raise
            return dict(self._state)

    def _run(self, service):
        try:
            first = service.list_sources(enabled=True, page=1, page_size=100)
            rows = list(first['items'])
            # Snapshot enabled sources; no default source is enabled implicitly.
            for page in range(2, (first['total'] + 99) // 100 + 1):
                rows.extend(service.list_sources(enabled=True, page=page, page_size=100)['items'])
            with self._lock:
                self._state['total'] = len(rows)
            for source in rows:
                try:
                    result = service.fetch_source(source['id'])
                    with self._lock:
                        self._state['saved_count'] += int(result.get('saved_count') or 0)
                except Exception:
                    # Existing fetch_source persists the sanitized per-source error.
                    with self._lock:
                        self._state['failed'] += 1
                finally:
                    with self._lock:
                        self._state['processed'] += 1
        except Exception:
            with self._lock:
                self._state['error'] = '读取资讯来源失败，请稍后重试；已有资讯保留。'
        finally:
            with self._lock:
                self._state['running'] = False
                self._state['finished_at'] = self._clock().isoformat()
