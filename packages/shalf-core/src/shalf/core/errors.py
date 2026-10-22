class ShalfError(Exception):
    """Base class for every error raised by shalf."""


class ConfigError(ShalfError):
    """Invalid or missing configuration."""


class PluginNotFoundError(ShalfError, KeyError):
    """A plugin type was requested that nobody registered."""
