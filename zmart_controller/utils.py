"""Utilities for drivers: where they plug in, how they are found, and whether they fit.

A driver registers a table of functions, one per command, under a
``connection`` dict. Three keys in that dict name the instrument: ``vendor``,
``microscope`` and ``api``. Any other keys are the driver's own, and go to its
``connect`` unchanged.

The registry checks only that a driver fits: every required function is
there, the three identity keys are present, and no other driver already
holds that name. Everything else is the driver's job.

A driver is a folder with a ``zmart.json`` naming its instruments and a
module holding its functions. :func:`register_driver` reads the file, checks
it, picks the functions by name and registers each instrument. It remembers
the driver in this computer's configuration folder, so later sessions plug it
in by themselves. A driver installed as a package can instead announce itself
through an entry point; see :func:`discover_installed_drivers`.

:func:`validate_driver` is for whoever writes a driver: it calls the
driver's ``get_*`` commands and checks the answers against the contract in
``docs/driver.md``. :func:`check_acquire_answer` does the same for one
acquisition, which the driver's own tests take, since checking it means
taking a picture.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import logging
import math
import os
import platform
import sys
from importlib.metadata import entry_points
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

# The keys that name an instrument. Any other key in a connection dict is the driver's own.
IDENTITY: tuple[str, ...] = ("vendor", "microscope", "api")

# (vendor, microscope, api) -> {"connection", "ops"}
REGISTRY: dict[tuple[str, ...], dict[str, Any]] = {}


def _identity(connection: dict[str, Any]) -> tuple[str, ...]:
    """The (vendor, microscope, api) triple of a connection dict."""
    missing = [key for key in IDENTITY if key not in connection]
    if missing:
        # Name keys only, never values: a connection dict may hold a password.
        raise ValueError(
            f"connection missing identity keys {missing}; has keys {sorted(connection)}"
        )
    return tuple(connection[key] for key in IDENTITY)


def register(connection: dict[str, Any], *, ops: dict[str, Any]) -> None:
    """Register a driver for one instrument.

    ``connection`` names the instrument and holds whatever the driver needs to
    connect. ``ops`` maps every name in :data:`OPS` to a function;
    ``disconnect`` is optional. Raises ``ValueError`` if a function or an
    identity key is missing.

    Registering the same driver again is harmless: its entry is simply
    refreshed. A *different* driver asking for a name another driver already
    holds is refused with ``ValueError``, naming both folders. The name is how
    an operator picks a microscope from the list, so letting a second driver
    take it over would quietly drive a different microscope than the one
    chosen.
    """
    missing = [name for name in OPS if name not in ops]
    if missing:
        raise ValueError(f"driver {_identity(connection)} missing ops: {missing}")
    key = _identity(connection)
    _refuse_a_name_held_by_another_driver(key, ops)
    # A full copy, nested settings included: later edits to the caller's dict,
    # or to a dict from get_instruments(), must never change what is stored.
    REGISTRY[key] = {"connection": copy.deepcopy(connection), "ops": ops}


def _refuse_a_name_held_by_another_driver(key: tuple[str, ...], ops: dict[str, Any]) -> None:
    """Raise ``ValueError`` when a different driver already holds this instrument's name."""
    held = REGISTRY.get(key)
    if held is not None and _origin(held["ops"]) != _origin(ops):
        raise ValueError(
            f"two drivers both call their instrument {' / '.join(key)}. The driver in "
            f"{_folder_of(held['ops'])} was plugged in first, and the driver in "
            f"{_folder_of(ops)} asks for the same name. Give one of them a different "
            f"vendor, microscope or api in its zmart.json."
        )


def _origin(ops: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Where each of a driver's functions was written: its module and its name there.

    Two tables with the same origins are the same driver, even when they were
    collected twice (once by folder, once by module name) or after the
    driver's module was loaded again.
    """
    return {
        name: (getattr(func, "__module__", ""), getattr(func, "__qualname__", repr(func)))
        for name, func in ops.items()
    }


def _folder_of(ops: dict[str, Any]) -> str:
    """The folder a driver's ``connect`` lives in, to name the driver in a message."""
    module = sys.modules.get(getattr(ops["connect"], "__module__", ""))
    path = getattr(module, "__file__", None)
    return str(Path(path).resolve().parent) if path else f"module {module!r}"


# The folder with the driver's controller-facing functions, inside a driver.
PLUGIN_FOLDER = "zmart_controller"


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


def _drivers_file() -> Path:
    return config_root() / "zmart_controller" / "utils.json"


def remembered_drivers() -> list[str]:
    """The drivers this computer plugs in by itself, as saved by :func:`register_driver`."""
    path = _drivers_file()
    if not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text())
    except ValueError as exc:
        raise RuntimeError(f"the driver list at {path} is not valid JSON: {exc}") from None
    return [str(entry) for entry in entries]


def _save_remembered(entries: list[str]) -> None:
    path = _drivers_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2) + "\n")
    except PermissionError:
        raise PermissionError(
            f"cannot write {path}. Run this once with the rights to write there, "
            f"or point ZMART_MICROSCOPY_ROOT at a folder you can write."
        ) from None


def forget_driver(driver: str | Path) -> bool:
    """Stop plugging a driver in at the start of later sessions.

    Returns whether it was on the list. The driver stays plugged in for the
    rest of this session.
    """
    key = _driver_key(driver)
    entries = remembered_drivers()
    if key not in entries:
        return False
    _save_remembered([e for e in entries if e != key])
    return True


def _driver_key(driver: str | Path) -> str:
    """How a driver is written down: the absolute path of its folder.

    A driver given by module name is written down by the folder it was found
    in, so a later session finds it even when started from somewhere else,
    where the name alone would no longer import. A name that cannot be found
    is kept as given.
    """
    path = Path(driver)
    if path.exists():
        return str(path.resolve())
    try:
        spec = importlib.util.find_spec(str(driver))
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.origin or not spec.origin.endswith("__init__.py"):
        return str(driver)
    return str(Path(spec.origin).parent.resolve())


CONTRACT = 1
MANIFEST = "zmart.json"


def register_driver(driver: str | Path, *, remember: bool = True) -> list[dict[str, Any]]:
    """Plug a driver in, and return the instruments it provides.

    ``driver`` is the driver's folder, or the name of an installed module.
    The controller looks there for ``zmart_controller/zmart.json`` (or
    ``zmart.json`` directly). That file names the instruments; the functions
    are found by name in the module next to it. See ``docs/driver.md`` for
    the contract.

    Run this once per driver on each microscope computer. The driver is
    remembered in this computer's configuration folder, and every later
    session plugs it in by itself when :func:`get_instruments` runs. Pass
    ``remember=False`` to plug it in for this session only. Calling it twice
    is harmless.

    Raises ``ValueError`` when nothing is found, the file is wrong, a
    function is missing, or a different driver already holds one of the
    instrument names, and says which.
    """
    plugin_dir, module = _locate_plugin(driver)
    manifest = _read_manifest(plugin_dir / MANIFEST)
    if module is None:
        module = _import_plugin(plugin_dir)
    ops = _collect_ops(module, plugin_dir)
    # Every name is checked before any is registered, so a refused driver adds nothing.
    for instrument in manifest["instruments"]:
        _refuse_a_name_held_by_another_driver(_identity(instrument), ops)
    added = []
    for instrument in manifest["instruments"]:
        register(instrument, ops=ops)
        added.append(copy.deepcopy(instrument))
    if remember:
        key = _driver_key(driver)
        entries = remembered_drivers()
        if key not in entries:
            _save_remembered(entries + [key])
    return added


def _locate_plugin(driver: str | Path):
    """Find the folder holding ``zmart.json``; import first if given a module name."""
    path = Path(driver)
    if path.is_dir():
        if (path / PLUGIN_FOLDER / MANIFEST).is_file() and (path / "__init__.py").is_file():
            return path / PLUGIN_FOLDER, _import_package(path)
        for candidate in (path / PLUGIN_FOLDER, path):
            if (candidate / MANIFEST).is_file():
                return candidate, None
        raise ValueError(f"no {PLUGIN_FOLDER}/{MANIFEST} found under {path}")
    if path.exists():
        raise ValueError(f"{path} is a file; give the driver's folder instead")
    try:
        module = importlib.import_module(str(driver))
    except ModuleNotFoundError as exc:
        if exc.name and str(driver).startswith(exc.name):
            raise ValueError(f"no driver found at {driver!s}") from None
        raise
    folder = Path(module.__file__).parent
    if (folder / MANIFEST).is_file():
        return folder, module
    if (folder / PLUGIN_FOLDER / MANIFEST).is_file():
        return folder / PLUGIN_FOLDER, importlib.import_module(f"{driver}.{PLUGIN_FOLDER}")
    raise ValueError(f"module {driver!s} has no {PLUGIN_FOLDER}/{MANIFEST}")


def _read_manifest(path: Path) -> dict[str, Any]:
    """Read and check a driver's ``zmart.json``."""
    try:
        manifest = json.loads(path.read_text())
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from None
    if not isinstance(manifest, dict) or manifest.get("contract") != CONTRACT:
        raise ValueError(
            f'{path} must say "contract": {CONTRACT}; this controller knows no other version'
        )
    instruments = manifest.get("instruments")
    if not isinstance(instruments, list) or not instruments:
        raise ValueError(f'{path} must list at least one instrument under "instruments"')
    for instrument in instruments:
        if not isinstance(instrument, dict):
            raise ValueError(f"{path}: every instrument must be an object")
        _identity(instrument)  # raises ValueError naming any missing identity key
    return manifest


def _import_package(package: Path):
    """Import a driver package by its own name, and return its ``zmart_controller`` module.

    A driver laid out as ``docs/driver.md`` describes reaches its own modules
    by their full names, such as ``acme_driver.vendor_interface``. Those
    imports only work when the package is imported under that name, so the
    folder above the package is added to Python's search path first. A
    different package of the same name that is already loaded is refused,
    since Python can hold only one of them.
    """
    package = package.resolve()
    top, parts = package, [package.name]
    while (top.parent / "__init__.py").is_file():
        top = top.parent
        parts.insert(0, top.name)
    name = ".".join(parts)
    loaded = sys.modules.get(parts[0])
    if loaded is not None and getattr(loaded, "__file__", None):
        if Path(loaded.__file__).resolve().parent != top:
            raise ValueError(
                f"cannot plug in {package}: another package named {parts[0]} is already "
                f"loaded from {Path(loaded.__file__).parent}. Rename one of the two drivers."
            )
    search_root = str(top.parent)
    if search_root not in sys.path:
        sys.path.append(search_root)
    module = importlib.import_module(f"{name}.{PLUGIN_FOLDER}")
    if Path(module.__file__).resolve().parent != package / PLUGIN_FOLDER:
        raise ValueError(
            f"cannot plug in {package}: the name {name} imports from "
            f"{Path(module.__file__).parent} instead. Rename one of the two drivers."
        )
    return module


def _import_plugin(plugin_dir: Path):
    """Import the plugin folder under a name of its own, so two drivers never clash."""
    name = f"zmart_controller__{plugin_dir.parent.name}_{abs(hash(str(plugin_dir.resolve()))):x}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, plugin_dir / "__init__.py", submodule_search_locations=[str(plugin_dir)]
    )
    if spec is None:
        raise ValueError(f"{plugin_dir} has no __init__.py beside its {MANIFEST}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def _collect_ops(module, plugin_dir: Path) -> dict[str, Any]:
    """Pick the driver's functions out of its module, by name."""
    ops = {}
    missing = []
    for name in OPS + ("disconnect",):
        func = getattr(module, name, None)
        if callable(func):
            ops[name] = func
        elif name != "disconnect":
            missing.append(name)
    if missing:
        raise ValueError(f"{plugin_dir} is missing these functions: {missing}")
    return ops


ENTRY_POINT_GROUP = "zmart_controller.drivers"

# True once installed and remembered drivers have been asked to register.
_discovered = False


def discover_installed_drivers() -> None:
    """Plug in the remembered and the installed drivers, once.

    Remembered drivers are those saved by :func:`register_driver`. An
    installed package announces itself with one line in its ``pyproject.toml``::

        [project.entry-points."zmart_controller.drivers"]
        acme = "zmart_drivers.acme:register"

    A driver that fails to load is logged and skipped, so one broken driver
    never hides the others.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True
    for entry in remembered_drivers():
        try:
            register_driver(entry, remember=False)
        except Exception:
            logger.exception("remembered driver %r could not be loaded; skipping it", entry)
    for entry_point in entry_points(group=ENTRY_POINT_GROUP):
        try:
            register_driver(entry_point.value.split(":")[0], remember=False)
        except Exception:
            logger.exception("driver %r could not be loaded; skipping it", entry_point.name)


def get_instruments() -> list[dict[str, Any]]:
    """List the available instruments, without connecting to anything.

    Each entry is a dict you can pass to :func:`set_instrument`. You may edit
    it first, for example to add a password. Installed driver packages are
    found here automatically.
    """
    discover_installed_drivers()
    return [copy.deepcopy(entry["connection"]) for _key, entry in sorted(REGISTRY.items())]


def resolve(instrument: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Find the driver for an instrument; return ``(ops, connection)``.

    Raises ``ValueError`` if no driver matches.
    """
    key = _identity(instrument)
    try:
        entry = REGISTRY[key]
    except KeyError:
        raise ValueError(
            f"no driver registered for {dict(zip(IDENTITY, key, strict=True))}; "
            f"known: {sorted(REGISTRY)}"
        ) from None
    return entry["ops"], instrument


# ---- validating a driver against the contract

AXES = ("x", "y", "z")


def validate_driver(instrument: dict[str, Any]) -> list[str]:
    """Connect to ``instrument`` and check every ``get_*`` answer against the contract.

    Returns the problems found, one sentence each. Empty means the driver fits.
    Raises whatever the driver raises on connect.
    """
    # Imported here: the session looks drivers up in this module.
    from .session import set_instrument

    problems: list[str] = []
    session = set_instrument(instrument)
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
        problems.append("get_actuators: the content must be a dict of axis -> list of motors")
        return
    for axis in AXES:
        motors = content.get(axis)
        if not isinstance(motors, list) or not motors:
            problems.append(f"get_actuators: axis {axis!r} must list at least one motor")


def _check_xyz(content, problems):
    if not isinstance(content, dict):
        problems.append("get_xyz: the content must be a dict of axis -> reading")
        return
    for axis in AXES:
        reading = content.get(axis)
        if not isinstance(reading, dict):
            problems.append(f"get_xyz: axis {axis!r} is missing")
            continue
        for key in ("value", "actuator", "unit", "range", "reach"):
            if key not in reading:
                problems.append(f"get_xyz: axis {axis!r} is missing {key!r}")
        rng = reading.get("range")
        if rng is not None and not (isinstance(rng, (list, tuple)) and len(rng) == 2):
            problems.append(f"get_xyz: axis {axis!r} range must be [min, max]")
            rng = None
        reach = reading.get("reach")
        if reach is not None:
            _check_reach(axis, reach, rng, problems)


def _is_number(value) -> bool:
    """True for an int or a float; True and False are not numbers here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_reach(axis, reach, travel, problems):
    """Check one axis's ``reach``: everywhere a picture can show along it.

    A picture taken at the edge of travel still shows half a field (or half
    a stack) further out, so reach is [min, max] in micrometers and always
    holds the travel range.
    """
    if not (
        isinstance(reach, (list, tuple))
        and len(reach) == 2
        and all(_is_number(end) for end in reach)
        and reach[0] <= reach[1]
    ):
        problems.append(
            f"get_xyz: axis {axis!r} reach must be [min, max] in micrometers, "
            f"with min no larger than max"
        )
        return
    if travel is not None and all(_is_number(end) for end in travel):
        if not (reach[0] <= travel[0] and travel[1] <= reach[1]):
            problems.append(
                f"get_xyz: axis {axis!r} reach {list(reach)} must contain "
                f"the travel range {list(travel)}"
            )


def _check_state(content, problems):
    if not isinstance(content, dict) or not isinstance(content.get("changeable"), dict):
        problems.append('get_state: the content must contain a "changeable" dict')
    if not isinstance(content, dict) or not isinstance(content.get("observed"), dict):
        problems.append('get_state: the content must contain an "observed" dict')


def _check_acquisition_settings(content, problems):
    if not isinstance(content, dict):
        problems.append(
            "get_acquisition_settings: the content must be a dict of setting -> choices"
        )
        return
    for name, spec in content.items():
        if not isinstance(spec, dict) or "options" not in spec or "active" not in spec:
            problems.append(f'get_acquisition_settings: {name!r} must have "options" and "active"')


def _check_procedures(content, problems):
    if not isinstance(content, dict):
        problems.append("get_procedures: the content must be a dict of name -> description")
        return
    for name, spec in content.items():
        if not isinstance(spec, dict) or "description" not in spec:
            problems.append(f'get_procedures: {name!r} must have a "description"')


# ---- checking one acquisition against the contract


def check_acquire_answer(answer: Any) -> list[str]:
    """Check what a driver's ``acquire`` answered against the contract.

    ``answer`` is the whole answer, ``{"success": ..., "content": ...}``. The
    content must name the ``position_label`` it was given, and list under ``files`` the path of every file the acquisition
    saved: the images and anything saved beside them. A format kept as a
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
#: micrometres it was taken at. docs/driver.md explains each one.
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
        return ["acquire: planes must be a list with one entry (a dict) per saved image plane"]
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
