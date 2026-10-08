"""Does a driver fit the controller? One call says which methods still answer wrongly.

Run it before installing a driver, with the same argument as ``register_driver``::

    zmart_controller.validate_driver("C:/drivers/my-scope/zmart_driver.json")

:func:`validate_driver` connects and checks every ``get_*`` answer.
:func:`check_acquire_answer` checks one acquisition, which the driver's own
tests take, since checking it means taking a picture.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .zmart_controller import ZmartController

#: The three axes every driver reports.
AXES = ("x", "y", "z")


def validate_driver(driver: Any, connection: dict[str, Any] | None = None) -> list[str]:
    """Connect to ``driver`` and check every ``get_*`` answer against the contract.

    ``driver`` is the driver's ``zmart_driver.json`` or its folder, as for
    ``register_driver``, or anything ``ZmartController`` accepts, such as a
    ``ZmartDriver`` class with its ``connection``. It moves nothing and
    acquires nothing.

    Returns the problems found, one sentence each. Empty means the driver fits.
    Raises whatever the driver raises on connect.
    """
    from .registry import load_driver

    if isinstance(driver, (str, Path)) and Path(driver).exists():
        driver = load_driver(driver)
    problems: list[str] = []
    session = ZmartController(driver, connection)
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
    # Whoever drives the microscope reads the description, so it has to say something.
    description = content.get("description") if isinstance(content, dict) else None
    if not (isinstance(description, str) and description.strip()):
        problems.append(
            "get_info: the content must contain description, text that describes the microscope"
        )


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
#: micrometres it was taken at. docs/2_plug_in_a_driver/README.md explains each one.
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
