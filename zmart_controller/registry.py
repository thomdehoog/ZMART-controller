"""The registry: the drivers installed on this computer, and where ZMART keeps its files.

A driver is installed once, with :func:`register_driver`, and from then on
every Python session on this computer can connect to it by name.
:func:`get_instruments` lists the installed drivers with the connection each
one will use, and :func:`remove_driver` takes one off the list. The list is
a small file in :func:`config_root`, the folder where drivers also keep what
they measure once per microscope, or in your home folder when that folder
cannot be written.

A driver made from the template is two files, ``zmart_driver.json`` and a
``ZmartDriver`` class; :func:`load_driver` reads them without installing.
A driver may also be a module with one function per command, found by name;
:func:`driver_functions` collects them and names any that are missing.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .zmart_controller import OPS

logger = logging.getLogger(__name__)


def driver_functions(driver: Any) -> dict[str, Any]:
    """The driver's functions, one per command, found by name.

    ``driver`` is a module such as ``zmart_controller.mock``, any object with
    the functions as attributes, or a dict from command name to function.
    ``disconnect`` is optional. Raises ``ValueError`` naming every missing
    function, so a half-finished driver is refused before it connects.
    """
    find = driver.get if isinstance(driver, dict) else lambda name: getattr(driver, name, None)
    ops = {name: find(name) for name in (*OPS, "disconnect")}
    missing = [name for name in OPS if not callable(ops[name])]
    if missing:
        raise ValueError(f"driver {driver_name(driver)} is missing functions: {missing}")
    return {name: func for name, func in ops.items() if func is not None}


def driver_name(driver: Any) -> str:
    """A short name for ``driver``, to show in messages: its module name if it has one."""
    return getattr(driver, "__name__", None) or type(driver).__name__


def config_root() -> Path:
    """The machine-wide folder where ZMART keeps its configuration.

    ``ZMART_MICROSCOPY_ROOT`` overrides it. Otherwise it is
    ``C:\\ProgramData\\zmart-microscopy`` on Windows,
    ``/Library/Application Support/zmart-microscopy`` on macOS and
    ``/etc/zmart-microscopy`` on Linux. The drivers keep their origin, limits
    and calibration under the same root.
    """
    override = os.environ.get("ZMART_MICROSCOPY_ROOT")
    if override:
        return Path(override)
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "zmart-microscopy"
    if system == "Darwin":
        return Path("/Library/Application Support/zmart-microscopy")
    return Path("/etc/zmart-microscopy")


# ---- the drivers registered on this computer

#: The name the mock driver is always listed under.
MOCK = "mock"
#: The file that lists the registered drivers, kept in the configuration folder.
REGISTRY_FILE = "drivers.json"


def user_root() -> Path:
    """The folder in your home folder used when :func:`config_root` cannot be written."""
    return Path.home() / ".zmart-microscopy"


def _registry_files() -> list[Path]:
    """The two places the list of drivers can live: the computer's, then your own."""
    return [config_root() / REGISTRY_FILE, user_root() / REGISTRY_FILE]


def _read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def _registered() -> dict[str, dict[str, Any]]:
    """Every registered driver, by name. An entry in your own list wins over the computer's."""
    entries: dict[str, dict[str, Any]] = {}
    for path in _registry_files():
        entries.update(_read(path))
    return entries


def _names() -> list[str]:
    """The names of the installed drivers, the mock first."""
    return [MOCK, *sorted(name for name in _registered() if name != MOCK)]


#: A connection key whose name holds one of these words is a secret, and is
#: never shown by :func:`get_instruments`.
SECRET_WORDS = ("password", "token", "secret")


def get_instruments() -> dict[str, dict[str, Any]]:
    """Every installed driver, by name, with the connection it will use.

    Pass any of the names to ``set_instrument``. The mock is always first.
    The connection is the dictionary ``set_instrument`` hands to the driver's
    ``connect`` when none is given: the one saved at ``register_driver``, or
    else the driver's own ``CONNECTION``. Secrets are left out: any key whose
    name contains ``password``, ``token`` or ``secret``. The mock has no
    connection and shows an empty one. A driver whose file can no longer be
    imported shows ``{"error": ...}`` instead, so one broken driver never
    hides the others.
    """
    instruments: dict[str, dict[str, Any]] = {}
    for name in _names():
        try:
            _, connection = find_driver(name)
        except Exception as exc:
            instruments[name] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        instruments[name] = {
            key: value
            for key, value in connection.items()
            if not any(word in key.lower() for word in SECRET_WORDS)
        }
    return instruments


#: The file in a driver that plugs into the controller.
PLUGIN_FILE = "zmart_controller_plugin.py"


def register_driver(plugin: str | Path, connection: dict[str, Any] | None = None) -> str:
    """Add a driver to this computer's list of drivers, once.

    ``plugin`` is the driver's folder, or its ``zmart_driver.json``: a driver
    made from the template is two files, ``zmart_driver.json`` with its name
    and connection and ``zmart_driver.py`` with its ``ZmartDriver`` class.
    A driver that brings its own ``zmart_controller_plugin.py`` is given by
    that file, or by the folder holding it; the plugin then gives the name,
    and may give the connection::

        NAME = "stellaris"
        CONNECTION = {"output_root": "D:/images"}   # optional

    The driver is loaded and checked first, so one that cannot be imported,
    or is missing a function or its name, is refused with a clear message
    and nothing is written. The connection is read each time the driver is
    plugged in; a ``connection`` given here is saved instead. Registering a
    driver again replaces its entry. Returns its name.
    """
    file = Path(plugin).resolve()
    if file.is_dir():
        file = file / (SETTINGS_FILE if (file / SETTINGS_FILE).is_file() else PLUGIN_FILE)
    if file.name == SETTINGS_FILE:
        loaded = load_driver(file)
        entry: dict[str, Any] = {"settings": str(file)}
    else:
        module, root = _module_of(file)
        loaded = _import(module, root)
        entry = {"file": str(file), "module": module, "root": root}
    if not hasattr(loaded, "ZmartDriver"):
        driver_functions(loaded)  # a two-file driver was checked by load_driver
    name = getattr(loaded, "NAME", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f'{file} must give the driver\'s NAME, such as NAME = "stellaris"')
    if name == MOCK:
        raise ValueError(f"{MOCK!r} is the mock driver's name; choose another NAME in {file}")
    if connection is not None:
        entry["connection"] = dict(connection)
    for path in _registry_files():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            entries = _read(path)
            entries[name] = entry
            path.write_text(json.dumps(entries, indent=2) + "\n")
            return name
        except OSError:
            logger.info("cannot write %s, trying the next place", path)
    raise PermissionError(f"could not write the list of drivers in {_registry_files()}")


def _module_of(file: Path) -> tuple[str, str]:
    """The import name of a driver's functions file, and the folder to import it from.

    A file inside a package is imported under its full package name, so the
    driver's own imports, relative ones included, work as usual. A file in a
    plain folder gets a name made from its full path, so two drivers that
    both call their file ``zmart_controller_plugin.py`` never get mixed up.
    """
    if not file.is_file():
        raise ValueError(f"the functions file {file} does not exist")
    parts, folder = [file.stem], file.parent
    while (folder / "__init__.py").is_file():
        parts.insert(0, folder.name)
        folder = folder.parent
    if len(parts) == 1:
        return f"{_FILE_PREFIX}{file}", str(folder)
    return ".".join(parts), str(folder)


# A module name starting with this is a driver file in a plain folder; the rest is its path.
_FILE_PREFIX = "file:"


def _import(module: str, root: str):
    # Add the driver's folder to the import path for this session, so the
    # driver's own imports work. A driver installed with pip needs none of this.
    if root not in sys.path:
        sys.path.insert(0, root)
    if not module.startswith(_FILE_PREFIX):
        return importlib.import_module(module)
    path = module[len(_FILE_PREFIX) :]
    name = "zmart_driver_" + "".join(c if c.isalnum() else "_" for c in path)
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[name] = loaded
        try:
            spec.loader.exec_module(loaded)
        except BaseException:
            del sys.modules[name]  # so a fixed file is read again next time
            raise
    return sys.modules[name]


def remove_driver(name: str) -> bool:
    """Take ``name`` off the list of registered drivers. Returns False if it was not there."""
    removed = False
    for path in _registry_files():
        entries = _read(path)
        if name in entries:
            del entries[name]
            path.write_text(json.dumps(entries, indent=2) + "\n")
            removed = True
    return removed


def find_driver(name: str) -> tuple[Any, dict[str, Any]]:
    """The driver registered as ``name``, imported, and the connection saved with it."""
    if name == MOCK:
        return importlib.import_module("zmart_controller.mock"), {}
    entry = _registered().get(name)
    if entry is None:
        raise ValueError(f"no driver installed as {name!r}; installed: {_names()}")
    if "settings" in entry:
        module = load_driver(entry["settings"])
    else:
        module = _import(entry["module"], entry["root"])
    if "connection" in entry:
        return module, dict(entry["connection"])
    return module, dict(getattr(module, "CONNECTION", None) or {})


#: The settings file a driver is installed from, and the class file it names by default.
SETTINGS_FILE = "zmart_driver.json"
DRIVER_FILE = "zmart_driver.py"


def load_driver(where: str | Path) -> SimpleNamespace:
    """The driver in the folder ``where``, or at that ``zmart_driver.json``, ready to plug in.

    Reads the name, the connection and the class file's path from
    ``zmart_driver.json`` (``driver``, relative to the JSON's folder,
    ``zmart_driver.py`` when left out), imports the ``ZmartDriver`` class
    from that file, and returns
    an object with ``NAME``, ``CONNECTION`` and the ``ZmartDriver`` class,
    which ``ZmartController``, ``set_instrument`` and
    ``register_driver`` all accept. Raises ``ValueError`` naming what is
    missing.
    """
    folder = Path(where).resolve()
    if folder.is_file():
        folder = folder.parent
    settings_file = folder / SETTINGS_FILE
    if not settings_file.is_file():
        raise ValueError(
            f"a driver is installed from its {SETTINGS_FILE}; {settings_file} is missing"
        )
    settings = json.loads(settings_file.read_text())
    name, connection = settings.get("name"), settings.get("connection") or {}
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f'{settings_file} must give the driver\'s "name"')
    driver_file = (folder / settings.get("driver", DRIVER_FILE)).resolve()
    if not driver_file.is_file():
        raise ValueError(f'{settings_file} names the class file "driver": {driver_file} is missing')
    module = _import(f"{_FILE_PREFIX}{driver_file}", str(driver_file.parent))
    driver_class = getattr(module, "ZmartDriver", None)
    if not isinstance(driver_class, type):
        raise ValueError(f"{driver_file} must define the class ZmartDriver")
    return SimpleNamespace(
        __name__=name, NAME=name, CONNECTION=dict(connection), ZmartDriver=driver_class
    )
