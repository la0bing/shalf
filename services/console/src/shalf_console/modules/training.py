from shalf_console.modules.base import ConsoleModule
from shalf_console.rbac import Permission


def module() -> ConsoleModule:
    """Planned: experiments, training runs and their datasets. The permission
    exists already so roles can be prepared before the module ships."""
    return ConsoleModule(
        key="training",
        title="Training",
        description="Experiments, training runs and point-in-time training datasets",
        status="planned",
        permissions=[Permission("training.read", "See experiments and training runs", "training")],
        read_permission="training.read",
        order=50,
    )
