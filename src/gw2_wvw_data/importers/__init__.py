"""Safe import adapters for third-party build sources."""


class ImportError(ValueError):
    """A remote build source is unsafe, malformed, or unsupported."""
