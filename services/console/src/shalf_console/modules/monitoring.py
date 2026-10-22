from shalf_console.modules.base import ConsoleModule
from shalf_console.rbac import Permission


def module() -> ConsoleModule:
    """Planned: feature/prediction drift and data quality dashboards."""
    return ConsoleModule(
        key="monitoring",
        title="Monitoring",
        description="Feature and prediction drift, data quality, freshness SLAs",
        status="planned",
        permissions=[Permission("monitoring.read", "See drift and data quality", "monitoring")],
        read_permission="monitoring.read",
        order=60,
    )
