"""The ZmartController: one microscope, driven through one method per command.

Make one with a driver, and it connects. The driver is a ``ZmartDriver``
class, two files made from the template, or an installed name::

    mic = ZmartController("my-scope")
    mic.set_xyz(100, 50, 0)

Each command calls the driver and answers ``{"success": bool, "content": ...}``.
``success`` says whether the driver did what was asked. ``content`` is what
the driver has to say about it. A ``ZmartDriver`` method returns plain
values for success; the functions at the end of this file turn them into
that answer. A method that raises :class:`NotConfirmed` is a soft failure,
answered as ``success: False`` with the text. Anything else it raises is
passed to the workflow unchanged: ``ValueError`` for a mistake in the
request, ``RuntimeError`` for a failure on the microscope.

The controller does no microscope work and checks nothing on the
microscope's behalf. Every check belongs to the driver, including whether
the connection is still open. Every call is synchronous: it returns when
the driver has finished. :func:`validate_driver` and
:func:`check_acquire_answer` check a driver's answers against this contract.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

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


class NotConfirmed(Exception):
    """Raise this from a ``ZmartDriver`` method for a soft failure: the command was
    sent, but what it asked for never showed up, and it is safe to carry on.

    The controller answers ``{"success": False, "content": error_text}``,
    where ``error_text`` is the message given here. Never raise it from
    ``set_xyz``: carrying on at an unknown position is not safe, so a move
    that cannot be confirmed raises ``RuntimeError``.
    """


class ZmartController:
    """One connected microscope, driven through one method per command.

    Make one with a driver, and it connects::

        mic = ZmartController("my-scope")
        mic.set_xyz(100, 50, 0)

    ``driver`` is the name of an installed driver, from ``get_instruments()``,
    a ``ZmartDriver`` class, what ``load_driver`` returns, or a module with
    one function per command such as ``zmart_controller.mock``. ``connection`` is handed to the driver's
    ``connect`` unchanged; left out, the driver's own connection is used.
    Raises ``ValueError`` naming any function the driver is missing.

    Each method calls the matching driver function and returns its answer.
    The controller keeps no state and refuses nothing. Its one public
    attribute, ``context``, names the driver: ``{"driver": ...}``.
    """

    def __init__(self, driver: Any, connection: dict[str, Any] | None = None) -> None:
        from .registry import driver_functions, driver_name, find_driver

        name = None
        if isinstance(driver, str):
            name = driver
            driver, saved = find_driver(name)
            connection = saved if connection is None else connection
        elif connection is None:
            connection = getattr(driver, "CONNECTION", None)
        connection = dict(connection or {})
        driver_class = driver if isinstance(driver, type) else getattr(driver, "ZmartDriver", None)
        if driver_class is not None:
            # A ZmartDriver class: making one connects, and the functions below
            # turn each of its methods into a command's answer.
            self._handle = driver_class(connection)
            self._ops = {function.__name__: function for function in _CLASS_FUNCTIONS}
        else:
            # A module with one function per command, such as the mock.
            self._ops = driver_functions(driver)
            self._handle = self._ops["connect"](connection)

        self.context = {"driver": name or driver_name(driver)}

    def _call(self, command: str, *args: Any, **kwargs: Any) -> dict:
        """Hand one command to the driver. A NotConfirmed from it is the soft answer."""
        try:
            return self._ops[command](self._handle, *args, **kwargs)
        except NotConfirmed as failure:
            return {"success": False, "content": str(failure)}

    # --- state and procedures ------------------------------------------------

    def get_state(self) -> dict:
        """Capture the instrument's settings so they can be applied again later.

        The ``content`` has two parts. ``"changeable"`` holds the settings that
        :meth:`set_state` applies. ``"observed"`` is a read-only description of
        the instrument. The controller does not look inside either.
        """
        return self._call("get_state")

    def set_state(self, state: dict) -> dict:
        """Apply a state captured with :meth:`get_state` (pass its ``content``).

        The driver applies the ``"changeable"`` part only. ``"observed"`` is
        never an instruction.
        """
        return self._call("set_state", state)

    def get_procedures(self) -> dict:
        """The routines this microscope offers, such as autofocus."""
        return self._call("get_procedures")

    def run_procedure(self, procedure: dict) -> dict:
        """Run one routine from :meth:`get_procedures`, chosen by ``{"name": ...}``."""
        return self._call("run_procedure", procedure)

    # --- movement -----------------------------------------------------------

    def get_actuators(self) -> dict:
        """The motors that can move each axis, e.g. ``{"z": ["motoric", "piezo"]}``.

        Pick one per axis with ``with_actuators`` on :meth:`get_xyz` and
        :meth:`set_xyz`.
        """
        return self._call("get_actuators")

    def get_xyz(self, with_actuators: dict | None = None) -> dict:
        """Read each axis: its position, and how far it can travel.

        Both in micrometres from the origin. ``with_actuators`` names a motor
        per axis, e.g. ``{"z": "piezo"}``. The names come from
        :meth:`get_actuators`; the driver checks them.
        """
        return self._call("get_xyz", with_actuators=with_actuators)

    def set_xyz(self, x: float, y: float, z: float, with_actuators: dict | None = None) -> dict:
        """Move to a position, in micrometres from the origin.

        ``with_actuators`` names the motor to use per axis. Left out, the
        driver uses its default. Any calibration is the driver's job.
        """
        return self._call("set_xyz", x, y, z, with_actuators=with_actuators)

    # --- acquire ---------------------------------------------------------------

    def get_acquisition_settings(self) -> dict:
        """The choices for capturing and saving, with allowed values and the active one.

        Asked of the driver afresh on every call.
        """
        return self._call("get_acquisition_settings")

    def acquire(self, position_label: str, acquisition_settings: dict | None = None) -> dict:
        """Capture an image here and save it, in one step.

        ``position_label`` names this position in the saved files, e.g.
        ``"A1"``. ``acquisition_settings`` holds choices from :meth:`get_acquisition_settings`;
        any left out keep their active value. The content lists every saved file
        under ``files``, so a workflow finds its pictures the same way on every
        microscope.
        """
        return self._call(
            "acquire", position_label=position_label, acquisition_settings=acquisition_settings
        )

    # --- information and lifecycle --------------------------------------------

    def get_info(self) -> dict:
        """Describe the connected setup.

        Every driver reports ``output_root``, the folder where images are
        saved. Anything else is an extra of that driver, and a workflow meant
        for any microscope should not rely on it.
        """
        return self._call("get_info")

    def disconnect(self) -> None:
        """Close the connection, if the driver has a way to close it."""
        disconnect = self._ops.get("disconnect")
        if disconnect is not None:
            disconnect(self._handle)


#: The old name of :class:`ZmartController`, kept so existing code keeps working.
Session = ZmartController


def set_instrument(driver: Any, connection: dict[str, Any] | None = None) -> ZmartController:
    """Plug in a driver, connect to its microscope, and return the :class:`ZmartController`.

    The same as ``ZmartController(driver, connection)``.
    """
    return ZmartController(driver, connection)


# ---- validating a driver against the contract


#: The three axes every driver reports.
AXES = ("x", "y", "z")


def validate_driver(driver: Any, connection: dict[str, Any] | None = None) -> list[str]:
    """Connect to ``driver`` and check every ``get_*`` answer against the contract.

    ``driver`` and ``connection`` are what you would pass to ``ZmartController``.
    It moves nothing and acquires nothing.

    Returns the problems found, one sentence each. Empty means the driver fits.
    Raises whatever the driver raises on connect.
    """
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


# ---- how a ZmartDriver's methods become a command's answer


def disconnect(handle):

    handle.disconnect()

    return None


def get_info(handle):

    output_root, description = handle.get_info()

    return {"success": True, "content": {"output_root": output_root, "description": description}}


def get_actuators(handle):

    x_motors, y_motors, z_motors = handle.get_actuators()

    return {"success": True, "content": {"x": x_motors, "y": y_motors, "z": z_motors}}


def get_xyz(handle, *, with_actuators=None):

    x, y, z, x_motor, y_motor, z_motor = handle.get_xyz(with_actuators)
    x_min, x_max, y_min, y_max, z_min, z_max = handle.get_canvas()

    return {
        "success": True,
        "content": {
            "x": {"value": x, "actuator": x_motor, "canvas": [x_min, x_max]},
            "y": {"value": y, "actuator": y_motor, "canvas": [y_min, y_max]},
            "z": {"value": z, "actuator": z_motor, "canvas": [z_min, z_max]},
        },
    }


def set_xyz(handle, x, y, z, *, with_actuators=None):

    x_motor, y_motor, z_motor = handle.set_xyz(x, y, z, with_actuators)

    return {
        "success": True,
        "content": {
            "position": {"x": x, "y": y, "z": z},
            "actuators": {"x": x_motor, "y": y_motor, "z": z_motor},
        },
    }


def get_state(handle):

    changeable, observed = handle.get_state()

    return {"success": True, "content": {"changeable": changeable, "observed": observed}}


def set_state(handle, state):

    applied = handle.set_state(state["changeable"])

    return {"success": True, "content": {"applied": applied}}


def get_acquisition_settings(handle):

    settings = handle.get_acquisition_settings()  # {name: {"options": [...], "active": value}}

    return {"success": True, "content": settings}


def acquire(handle, *, position_label, acquisition_settings=None):

    files, planes = handle.acquire(position_label, acquisition_settings)

    return {
        "success": True,
        "content": {
            "position_label": position_label,
            "files": files,  # the path of every file saved
            "planes": planes,  # [{"path", "c", "z", "t", "x_um", "y_um", "z_um"}, ...]
        },
    }


def get_procedures(handle):

    procedures = handle.get_procedures()  # {name: {"description": ...}}

    return {"success": True, "content": procedures}


def run_procedure(handle, procedure):

    handle.run_procedure(procedure)

    return {"success": True, "content": {"ran": procedure["name"]}}


#: The functions above, one per command. Each takes the ZmartDriver as the handle.
_CLASS_FUNCTIONS = (
    disconnect,
    get_info,
    get_actuators,
    get_xyz,
    set_xyz,
    get_state,
    set_state,
    get_acquisition_settings,
    acquire,
    get_procedures,
    run_procedure,
)
