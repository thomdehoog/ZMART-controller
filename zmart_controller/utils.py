"""Utilities for drivers: what a driver must hold, and whether it fits.

A driver is the whole set of files that talks to one microscope. Towards the
controller it offers one function per command, found by name on a module (or
any object, or a dict). :func:`driver_functions` collects them and names any
that are missing. Everything else is the driver's job.

:func:`validate_driver` is for whoever writes a driver: it calls the
driver's ``get_*`` commands and checks the answers against the contract in
``docs/1_plug_in_a_driver``. :func:`check_acquire_answer` does the same for
one acquisition, which the driver's own tests take, since checking it means
taking a picture.

:func:`register_driver` adds a driver's ``zmart_controller_plugin.py`` to this
computer's list once, under the ``NAME`` it gives. :func:`get_drivers`
lists the registered names, :func:`get_instruments` adds the connection each
one will use, and ``set_instrument`` accepts any of the names. The
list is a small file in :func:`config_root`, or in your home folder when that
folder cannot be written.

:func:`config_root` is also the folder where drivers keep what they measure
once per microscope: the origin, the travel limits and the calibration.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import math
import os
import platform
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Every driver must provide a function for each of these. disconnect is optional.
OPS: tuple[str, ...] = (
    "connect",
    "get_acquisition_settings",
    "get_actuators",
    "get_xyz",
    "set_xyz",
    "acquire",
    "get_state",
    "set_state",
    "get_procedures",
    "run_procedure",
    "get_info",
)


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


def get_drivers() -> list[str]:
    """The names of the drivers registered on this computer, the mock first.

    Pass any of them to ``set_instrument``.
    """
    return [MOCK, *sorted(name for name in _registered() if name != MOCK)]


#: A connection key whose name holds one of these words is a secret, and is
#: never shown by :func:`get_instruments`.
SECRET_WORDS = ("password", "token", "secret")


def get_instruments() -> dict[str, dict[str, Any]]:
    """Every installed driver, by name, with the connection it will use.

    The connection is the dictionary ``set_instrument`` hands to the driver's
    ``connect`` when none is given: the one saved at ``register_driver``, or
    else the driver's own ``CONNECTION``. Secrets are left out: any key whose
    name contains ``password``, ``token`` or ``secret``. The mock has no
    connection and shows an empty one. A driver whose file can no longer be
    imported shows ``{"error": ...}`` instead, so one broken driver never
    hides the others.
    """
    instruments: dict[str, dict[str, Any]] = {}
    for name in get_drivers():
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

    ``plugin`` is the driver's ``zmart_driver.json``, the file that holds the
    driver's name and how to reach the microscope, or its
    ``zmart_controller_plugin.py``, the file with the functions the
    controller calls, or the folder holding them. The plugin gives the
    driver's name, and may give its configuration, in a driver made from
    the template by reading them from the JSON file next to it::

        NAME = "stellaris"
        CONNECTION = {"output_root": "D:/images"}   # optional

    The functions are imported and checked first, so a file that cannot be
    imported, or is missing a function or its ``NAME``, is refused with a
    clear message and nothing is written. ``CONNECTION`` is read each time
    the driver is plugged in; a ``connection`` given here is saved instead.
    Registering a driver again replaces its entry. Returns its name.
    """
    file = Path(plugin).resolve()
    if file.is_dir():
        file = file / PLUGIN_FILE
    elif file.suffix == ".json":
        file = file.with_name(PLUGIN_FILE)  # the settings file sits next to the plugin
    module, root = _module_of(file)
    loaded = _import(module, root)
    driver_functions(loaded)
    name = getattr(loaded, "NAME", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f'{file} must give the driver\'s NAME, such as NAME = "stellaris"')
    if name == MOCK:
        raise ValueError(f"{MOCK!r} is the mock driver's name; choose another NAME in {file}")
    entry = {"file": str(file), "module": module, "root": root}
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
        raise ValueError(f"no driver registered as {name!r}; registered: {get_drivers()}")
    module = _import(entry["module"], entry["root"])
    if "connection" in entry:
        return module, dict(entry["connection"])
    return module, dict(getattr(module, "CONNECTION", None) or {})


# ---- validating a driver against the contract

#: The three axes every driver reports.
AXES = ("x", "y", "z")


def validate_driver(driver: Any, connection: dict[str, Any] | None = None) -> list[str]:
    """Connect to ``driver`` and check every ``get_*`` answer against the contract.

    ``driver`` and ``connection`` are what you would pass to ``set_instrument``.
    It moves nothing and acquires nothing.

    Returns the problems found, one sentence each. Empty means the driver fits.
    Raises whatever the driver raises on connect.
    """
    # Imported here: the session collects the driver's functions with this module.
    from .session import set_instrument

    problems: list[str] = []
    session = set_instrument(driver, connection)
    try:
        checks = {
            "get_info": _check_info,
            "get_actuators": _check_actuators,
            "get_xyz": _check_xyz,
            "get_state": _check_state,
            "get_acquisition_settings": _check_acquisition_settings,
            "get_procedures": _check_procedures,
        }
        for name, check in checks.items():
            try:
                answer = getattr(session, name)()
            except Exception as exc:
                problems.append(f"{name} raised {type(exc).__name__}: {exc}")
                continue
            content = _envelope(name, answer, problems)
            if content is not None:
                check(content, problems)
    finally:
        session.disconnect()
    return problems


def _envelope(name: str, answer: Any, problems: list[str]):
    """Check the ``{"success", "content"}`` shape; return the content, or None."""
    if not isinstance(answer, dict) or not {"success", "content"} <= set(answer):
        problems.append(
            f'{name} must return {{"success": ..., "content": ...}}, got {type(answer).__name__}'
        )
        return None
    if not isinstance(answer["success"], bool):
        problems.append(f"{name}: success must be True or False")
    return answer["content"]


def _check_info(content, problems):
    if not isinstance(content, dict) or "output_root" not in content:
        problems.append("get_info: the content must contain output_root")
        return
    # Optional: a driver may leave the description out. When it is there it
    # has to say something, because whoever drives the microscope reads it.
    description = content.get("description")
    if "description" in content and not (isinstance(description, str) and description.strip()):
        problems.append("get_info: description must be text that describes the microscope")


def _check_actuators(content, problems):
    if not isinstance(content, dict):
        problems.append("get_actuators: the content must map each axis to a list of motor names")
        return
    for axis in AXES:
        motors = content.get(axis)
        if not isinstance(motors, list) or not motors:
            problems.append(f"get_actuators: axis {axis!r} must list at least one motor")


def _check_xyz(content, problems):
    if not isinstance(content, dict):
        problems.append("get_xyz: the content must map each axis to its reading")
        return
    for axis in AXES:
        reading = content.get(axis)
        if not isinstance(reading, dict):
            problems.append(f"get_xyz: axis {axis!r} is missing")
            continue
        for key in ("value", "actuator", "canvas"):
            if key not in reading:
                problems.append(f"get_xyz: axis {axis!r} is missing {key!r}")
        canvas = reading.get("canvas")
        if canvas is not None:
            _check_canvas(axis, canvas, problems)


def _is_number(value) -> bool:
    """True for an int or a float; True and False are not numbers here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_canvas(axis, canvas, problems):
    """Check one axis's ``canvas``: everywhere a picture can show along it, [min, max]."""
    if not (
        isinstance(canvas, (list, tuple))
        and len(canvas) == 2
        and all(_is_number(end) for end in canvas)
        and canvas[0] <= canvas[1]
    ):
        problems.append(
            f"get_xyz: axis {axis!r} canvas must be [min, max] in micrometres, "
            f"with min no larger than max"
        )


def _check_state(content, problems):
    if not isinstance(content, dict) or not isinstance(content.get("changeable"), dict):
        problems.append(
            'get_state: the content must contain "changeable", a dictionary of settings'
        )
    if not isinstance(content, dict) or not isinstance(content.get("observed"), dict):
        problems.append('get_state: the content must contain "observed", a dictionary')


def _check_acquisition_settings(content, problems):
    if not isinstance(content, dict):
        problems.append(
            "get_acquisition_settings: the content must map each setting to its choices"
        )
        return
    for name, spec in content.items():
        if not isinstance(spec, dict) or "options" not in spec or "active" not in spec:
            problems.append(f'get_acquisition_settings: {name!r} must have "options" and "active"')


def _check_procedures(content, problems):
    if not isinstance(content, dict):
        problems.append(
            "get_procedures: the content must map each procedure name to its description"
        )
        return
    for name, spec in content.items():
        if not isinstance(spec, dict) or "description" not in spec:
            problems.append(f'get_procedures: {name!r} must have a "description"')


# ---- checking one acquisition against the contract


def check_acquire_answer(answer: Any) -> list[str]:
    """Check what a driver's ``acquire`` answered against the contract.

    ``answer`` is the whole answer, ``{"success": ..., "content": ...}``. The
    content must name the ``position_label`` it was given, and list under
    ``files`` the path of every file the acquisition saved: the images and
    anything saved beside them. A format kept as a
    folder, such as OME-Zarr, is listed by its folder. Every path must exist.
    This is how a workflow finds the pictures on any microscope, so a driver
    that keeps them under a name of its own works with none of them.

    ``planes`` then says, for every saved image plane, which file it is in,
    which channel, depth and moment it is (``c``, ``z`` and ``t``, each
    counted from 0, which also find the plane inside a file that holds many),
    and where on the sample it was taken (``x_um``, ``y_um`` and ``z_um``,
    the stage position in micrometres, or None where the driver cannot know
    it). Every file a plane names must be in ``files``, and no two planes may
    share the same channel, depth and moment. A driver may add entries of its
    own to a plane; they are not checked.

    An acquisition that did not succeed may list no files and no planes.
    Returns the problems found, one sentence each; empty means the answer fits.

    :func:`validate_driver` cannot take a picture, because it must never move
    or expose anything. A driver's own tests call this after an acquisition
    instead, on a simulator or a test bench.
    """
    problems: list[str] = []
    content = _envelope("acquire", answer, problems)
    if content is None:
        return problems
    if not isinstance(content, dict):
        return problems + ["acquire: the content must be a dict"]
    if "position_label" not in content:
        problems.append("acquire: the content must contain position_label")
    if "files" not in content:
        problems.append(
            "acquire: the content must contain files, the list of paths of every file it saved"
        )
        return problems
    files = content["files"]
    if not isinstance(files, list) or not all(isinstance(path, str) for path in files):
        problems.append("acquire: files must be a list of paths, one per saved file")
        return problems
    if answer.get("success") is True and not files:
        problems.append("acquire: a successful acquisition must list at least one file in files")
    for path in files:
        if not Path(path).exists():
            problems.append(f"acquire: files names {path}, which does not exist")
    return problems + _plane_problems(answer.get("success") is True, content, files)


#: What every entry of the ``planes`` in acquire's content holds: the file, the
#: plane's channel, depth and moment counted from 0, and the stage position in
#: micrometres it was taken at. docs/1_plug_in_a_driver/README.md explains each one.
_PLANE_COUNTS = ("c", "z", "t")
_PLANE_POSITION_UM = ("x_um", "y_um", "z_um")
_PLANE_KEYS = ("path", *_PLANE_COUNTS, *_PLANE_POSITION_UM)


def _plane_problems(succeeded: bool, content: dict, files: list[str]) -> list[str]:
    """The problems with the ``planes`` in acquire's content, one sentence each.

    The planes are how a workflow knows where each saved picture sits on the
    sample, so each entry is checked on its own and the sentence names it by
    its place in the list (``planes[0]`` is the first).
    """
    if "planes" not in content:
        return [
            "acquire: the content must contain planes, one entry per saved image saying which "
            "file, channel, depth and stage position it is"
        ]
    planes = content["planes"]
    if not isinstance(planes, list) or not all(isinstance(plane, dict) for plane in planes):
        return ["acquire: planes must be a list with one dictionary per saved image plane"]
    problems: list[str] = []
    if succeeded and not planes:
        problems.append(
            "acquire: a successful acquisition must describe at least one image plane in planes"
        )
    listed = {str(Path(path)) for path in files}
    seen: set[tuple[int, int, int]] = set()
    for number, plane in enumerate(planes):
        name = f"acquire: planes[{number}]"
        missing = [key for key in _PLANE_KEYS if key not in plane]
        if missing:
            problems.append(f"{name} must contain {', '.join(missing)}")
            continue
        path = plane["path"]
        if not isinstance(path, str) or str(Path(path)) not in listed:
            problems.append(f"{name} names {path}, which is not in files")
        counts_fit = True
        for key in _PLANE_COUNTS:
            value = plane[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                problems.append(f"{name} {key} must be a whole number from 0, got {value!r}")
                counts_fit = False
        for key in _PLANE_POSITION_UM:
            value = plane[key]
            if value is None:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                problems.append(
                    f"{name} {key} must be a number of micrometres, or None when unknown, "
                    f"got {value!r}"
                )
        if counts_fit:
            slot = (plane["c"], plane["z"], plane["t"])
            if slot in seen:
                problems.append(
                    f"{name} repeats channel {slot[0]}, depth {slot[1]} and time {slot[2]} "
                    "of an earlier plane"
                )
            seen.add(slot)
    return problems
