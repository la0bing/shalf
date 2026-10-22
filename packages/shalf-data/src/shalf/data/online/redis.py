from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from shalf.data.feature_view import BaseFeatureView
from shalf.data.online.base import (
    OnlineRecord,
    OnlineStore,
    decode_values,
    encode_values,
    from_micros,
    online_store_registry,
    to_micros,
)

# Compare-and-set so older event timestamps never overwrite newer ones, and
# keys expire once their values fall outside the view's ttl.
_WRITE_SCRIPT = """
local current = redis.call('HGET', KEYS[1], 'ts')
if current and tonumber(current) > tonumber(ARGV[2]) then
  return 0
end
redis.call('HSET', KEYS[1], 'payload', ARGV[1], 'ts', ARGV[2])
if tonumber(ARGV[3]) > 0 then
  redis.call('PEXPIREAT', KEYS[1], ARGV[3])
end
return 1
"""


@online_store_registry.register("redis")
class RedisOnlineStore(OnlineStore):
    """Redis hashes keyed ``shalf:{project}:{view}:{entity_key}``.

    The production default: shared by every feature-server replica.
    ``pip install shalf-data[redis]``.
    """

    def __init__(
        self, *, url: str = "redis://localhost:6379/0", client: Any = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.url = url
        self._client = client
        self._script: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import redis
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise ImportError(
                    "RedisOnlineStore requires `pip install shalf-data[redis]`"
                ) from exc
            self._client = redis.Redis.from_url(self.url)
        return self._client

    def ping(self) -> None:
        self.client.ping()

    def _key(self, view_name: str, entity_key: str) -> str:
        return f"shalf:{self.project}:{view_name}:{entity_key}"

    def write_records(self, view: BaseFeatureView, records: Sequence[OnlineRecord]) -> int:
        if self._script is None:
            self._script = self.client.register_script(_WRITE_SCRIPT)
        pipe = self.client.pipeline(transaction=False)
        for record in records:
            expire_at = 0
            if view.ttl is not None:
                expire_at = int((record.event_timestamp + view.ttl).value // 1_000_000)
            self._script(
                keys=[self._key(view.name, record.entity_key)],
                args=[encode_values(record.values), to_micros(record.event_timestamp), expire_at],
                client=pipe,
            )
        return int(sum(pipe.execute()))

    def read_records(
        self, view: BaseFeatureView, entity_keys: Sequence[str]
    ) -> list[OnlineRecord | None]:
        pipe = self.client.pipeline(transaction=False)
        for key in entity_keys:
            pipe.hgetall(self._key(view.name, key))
        results: list[OnlineRecord | None] = []
        for key, raw in zip(entity_keys, pipe.execute(), strict=True):
            if not raw:
                results.append(None)
                continue
            raw = {k.decode() if isinstance(k, bytes) else k: v for k, v in raw.items()}
            results.append(OnlineRecord(key, decode_values(raw["payload"]), from_micros(raw["ts"])))
        return results

    def _watermark_key(self, view_name: str) -> str:
        return f"shalf:{self.project}:__watermark__:{view_name}"

    def get_watermark(self, view_name: str) -> pd.Timestamp | None:
        value = self.client.get(self._watermark_key(view_name))
        return from_micros(value) if value is not None else None

    def set_watermark(self, view_name: str, value: pd.Timestamp) -> None:
        self.client.set(self._watermark_key(view_name), to_micros(value))

    def teardown(self) -> None:
        for key in self.client.scan_iter(match=f"shalf:{self.project}:*"):
            self.client.delete(key)
