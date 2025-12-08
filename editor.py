#!/usr/bin/env python3
"""Thin wrapper entry point that imports and runs the editor from the packaged module.

This wrapper works when the package is installed (normal), or when running the
repository from source (not installed). It falls back to loading the module
from the local `librenms_weathermap/editor.py` file if needed, so `python
editor.py` works without Poetry.
"""

from importlib import import_module
import importlib
import importlib.util
import os
import sys


def _load_local_module(module_name, filepath):
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    # Try normal import (this will work when the package is installed)
    try:
        mod = import_module('librenms_weathermap.editor')
    except Exception:
        # Fall back: find the local package module file and import from path
        base = os.path.dirname(__file__)
        pkg_file = os.path.join(base, 'librenms_weathermap', 'editor.py')
        if os.path.exists(pkg_file):
            mod = _load_local_module('local_librenms_weathermap_editor', pkg_file)
        else:
            raise
    return mod.main()


if __name__ == '__main__':
    main()
