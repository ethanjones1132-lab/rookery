"""Load this plugin's engine package under a stable, path-scoped private name.

Hermes loads the plugin root as a package, while the dashboard loads
``dashboard/plugin_api.py`` as a standalone module. Both entry points call this
bootstrap so they share the same engine modules without changing ``sys.path``.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
from importlib import _bootstrap as _import_bootstrap
import os
import sys
from pathlib import Path
from types import ModuleType


def _namespace(plugin_root: Path) -> str:
    identity = os.path.normcase(str(plugin_root.resolve()))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"_rookery_engine_{digest}"


def load_engine(plugin_root: str | os.PathLike[str]) -> ModuleType:
    """Return the engine package for ``plugin_root``, verifying any cached origin."""
    root = Path(plugin_root).resolve(strict=True)
    init_file = (root / "rookery" / "__init__.py").resolve(strict=True)
    package_name = _namespace(root)
    # Separate standalone/root helper imports share importlib's per-module lock.
    module_lock = _import_bootstrap._get_module_lock(package_name)
    module_lock.acquire()
    try:
        cached = sys.modules.get(package_name)
        if cached is not None:
            origin = getattr(cached, "__file__", None)
            paths = getattr(cached, "__path__", ())
            if origin is None or Path(origin).resolve() != init_file or not any(
                Path(path).resolve() == init_file.parent for path in paths
            ):
                raise ImportError(f"Rookery engine namespace origin mismatch: {package_name}")
            return cached

        spec = importlib.util.spec_from_file_location(
            package_name, init_file, submodule_search_locations=[str(init_file.parent)]
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load Rookery engine from {init_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = module
        try:
            spec.loader.exec_module(module)
            for child in ("events", "project", "service", "tools", "export"):
                importlib.import_module(f"{package_name}.{child}")
        except BaseException:
            for name in tuple(sys.modules):
                if name == package_name or name.startswith(package_name + "."):
                    sys.modules.pop(name, None)
            raise
        return module
    finally:
        module_lock.release()


__all__ = ["load_engine"]
