from __future__ import annotations

from typing import Any, ClassVar

from shalf.data.sources.base import source_registry
from shalf.data.sources.sql import SQLDataSource


@source_registry.register("postgres")
class PostgresSource(SQLDataSource):
    """PostgreSQL source (``pip install shalf-data[postgres]``).

    ``dsn`` is a libpq connection string, e.g.
    ``postgresql://user:pass@host:5432/db``. Prefer passing it via an
    environment variable / Kubernetes secret rather than hard-coding it.
    """

    type_name: ClassVar[str] = "postgres"
    paramstyle: ClassVar[str] = "format"

    def __init__(
        self, *, dsn: str, connect_kwargs: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.dsn = dsn
        self.connect_kwargs = dict(connect_kwargs or {})

    def connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ImportError("PostgresSource requires `pip install shalf-data[postgres]`") from exc
        return psycopg.connect(self.dsn, **self.connect_kwargs)

    def describe(self) -> dict[str, Any]:
        # Never leak credentials through the registry API.
        return {**super().describe(), "dsn": "<redacted>"}
