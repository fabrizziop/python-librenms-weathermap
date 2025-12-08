#!/usr/bin/env python3
"""Thin wrapper entry point for the weathermap that defers to the packaged function."""

from importlib import import_module
import importlib.util
import os
import importlib


def _load_local_module(module_name, filepath):
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    # Try normal import (works when package is installed)
    try:
        mod = import_module('librenms_weathermap.main')
    except Exception:
        # Fall back to local file in repository
        base = os.path.dirname(__file__)
        pkg_file = os.path.join(base, 'librenms_weathermap', 'main.py')
        if os.path.exists(pkg_file):
            mod = _load_local_module('local_librenms_weathermap_main', pkg_file)
        else:
            raise
    return mod.main()


if __name__ == '__main__':
    main()