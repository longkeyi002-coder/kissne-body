"""Bundled ``kissne_mobile`` platform plugin — package entry point.

The repo's plugin loader imports this package and calls ``register(ctx)``; the
implementation lives in :mod:`plugins.platforms.kissne_mobile.adapter` and the
device credential layer in :mod:`plugins.platforms.kissne_mobile.device_store`.
"""

from .adapter import register

__all__ = ["register"]
