from collections import Counter
from threading import Lock

class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._request_counts = Counter()
        self._status_counts = Counter()
        self._auth_events = Counter()

    def record_request(self, path: str, method: str, status_code: int) -> None:
        with self._lock:
            self._request_counts[f"{method} {path}"] += 1
            self._status_counts[str(status_code)] += 1

    def record_auth_event(self, event_type: str, status: str) -> None:
        with self._lock:
            self._auth_events[f"{event_type}:{status}"] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "requests": dict(self._request_counts),
                "statuses": dict(self._status_counts),
                "auth_events": dict(self._auth_events),
            }
