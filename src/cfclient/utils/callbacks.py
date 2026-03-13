"""
Simple callback utilities (previously provided by cflib).

Caller is an observer-pattern helper: register callbacks with add_callback(),
remove them with remove_callback(), and fire all registered callbacks by
calling the Caller instance.
"""


class Caller:
    """Container for managing and invoking a list of callbacks."""

    def __init__(self):
        self._callbacks = []

    def add_callback(self, cb):
        """Register a callback (ignored if already registered)."""
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def remove_callback(self, cb):
        """Remove a previously registered callback."""
        self._callbacks.remove(cb)

    def call(self, *args, **kwargs):
        """Invoke all registered callbacks with the given arguments."""
        copy = list(self._callbacks)
        for cb in copy:
            cb(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        self.call(*args, **kwargs)
