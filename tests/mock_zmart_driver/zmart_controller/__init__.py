"""The mock microscope's ZMART controller plugin: the 11 functions.

This is part 8 of the driver anatomy. It presents the driver to the ZMART
Controller in the shape every microscope shares, and it does nothing else:
no coordinate arithmetic and no safety checks of its own. Those happened
further down. Each function here only maps a controller command onto the
driver's get actions, set actions, procedures and data handling.

The mock is a complete driver, built from the same parts a real one has::

    vendor_interface/   talks to MockScope Control, the pretend vendor software
    error_handling/     sorts every problem into a kind, and says what to do
    get_actions/       asks the microscope things, through the get dispatcher
    set_actions/       changes the microscope, through the set dispatcher
    procedures/         recipes: autofocus, backlash takeup, parking the piezo
    data_handling/      turns the vendor's files into OME-TIFF or OME-Zarr
    configuration/      origin, registration, limits, calibration
    zmart_controller/   this plugin
    testing/            the mock API and everything else for testing

Plug it in like any driver::

    zmart_controller.register_driver("mock_zmart_driver")

The connection dictionary may hold ``output_root`` (where images are
saved), ``token`` (the vendor login, default ``"mock-token"``) and
``mock_timing``: ``"realistic"`` (the default) lets moves and acquisitions
take time, ``"instant"`` makes them finish at once.

Every function except ``connect`` and ``disconnect`` takes the handle first
and returns ``{"success": bool, "content": ...}``.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import inspect
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mock_zmart_driver import get_actions as get
from mock_zmart_driver import set_actions as setter
from mock_zmart_driver.configuration import Configuration, load_configuration, user_range
from mock_zmart_driver.data_handling import FORMATS, CommandLog, save_acquisition
from mock_zmart_driver.data_handling.save import safe_name
from mock_zmart_driver.error_handling import classify
from mock_zmart_driver.get_actions import GetDispatcher
from mock_zmart_driver.procedures import PROCEDURES
from mock_zmart_driver.set_actions import Gate, SetDispatcher
from mock_zmart_driver.vendor_interface import NAME_LIMIT, MockScopeConnection

logger = logging.getLogger("mock_zmart_driver")

# Where images go when the connection does not say: a folder in the
# computer's temporary space, so trying the mock never litters a project.
DEFAULT_OUTPUT_ROOT = Path(tempfile.gettempdir()) / "zmart-mock-output"

# The order in which set_state applies settings: the objective first, since
# changing it can change what the other settings mean.
_STATE_ORDER = ("objective", "laser_power", "gain", "exposure_ms")


@dataclass
class MockHandle:
    """Everything a connected mock driver holds.

    ``vendor`` is the connection to MockScope Control (``vendor.scope`` is
    the pretend software itself, for tests). ``get`` and ``set`` are the two
    dispatchers, ``config`` the configuration loaded at connect, ``log`` the
    command log, and ``output_root`` the folder where images are saved.
    ``camera`` is the camera's frame in pixels, read once at connect: it
    never changes while the software runs.
    """

    vendor: MockScopeConnection
    config: Configuration
    get: GetDispatcher
    set: SetDispatcher
    log: CommandLog
    output_root: Path
    identity: tuple[str, str, str]
    client: Any = None
    closed: bool = False
    software: dict[str, str] = field(default_factory=dict)
    camera: dict[str, int] = field(default_factory=dict)

    @property
    def scope(self):
        """The pretend vendor software, for tests that make it misbehave."""
        return self.vendor.scope


def _answer(content: Any, *, success: bool = True) -> dict:
    """Wrap the content in the shape every command returns."""
    return {"success": success, "content": content}


def _require_open(handle: MockHandle) -> None:
    if handle.closed:
        raise RuntimeError("session is disconnected")


# --- connecting ---------------------------------------------------------------


def connect(connection: dict) -> MockHandle:
    """Start the pretend vendor software, check it, and load this microscope's configuration.

    The steps, in order: start the software and log in; load the
    configuration (machine description, registration and origin, then the
    limits, which switch on the limits gate, then the calibration); check
    the software's version and serial number against the machine
    description. If any step fails, the software is closed again and the
    error is raised.
    """
    identity = (connection["vendor"], connection["microscope"], connection["api"])
    output_root = Path(connection.get("output_root") or DEFAULT_OUTPUT_ROOT)
    output_root.mkdir(parents=True, exist_ok=True)
    timing = connection.get("mock_timing", "realistic")
    if timing not in ("realistic", "instant"):
        raise ValueError(f"mock_timing must be 'realistic' or 'instant', not {timing!r}")
    vendor = MockScopeConnection.start(
        output_folder=output_root / "_vendor_raw",
        token=connection.get("token", "mock-token"),
        instant=timing == "instant",
    )
    try:
        log = CommandLog()
        config = load_configuration(identity)
        handle = MockHandle(
            vendor=vendor,
            config=config,
            get=GetDispatcher(classify=classify, record=log.record),
            set=SetDispatcher(gate=Gate(config.limits), classify=classify, record=log.record),
            log=log,
            output_root=output_root,
            identity=identity,
            client=connection.get("client"),
        )
        handle.software = get.version(handle).value_or_raise("the software version")
        hardware = get.hardware(handle).value_or_raise("the hardware description")
        _check_machine(handle, hardware["serial"])
        handle.camera = {
            "width": hardware["camera"]["width"],
            "height": hardware["camera"]["height"],
        }
    except BaseException:
        vendor.close()
        raise
    return handle


def _check_machine(handle: MockHandle, serial: str) -> None:
    """Refuse a configuration that belongs to another microscope; warn about an untested version."""
    machine = handle.config.machine_description
    if serial != machine["serial"]:
        raise RuntimeError(
            f"this microscope reports serial {serial}, but the configuration in "
            f"{handle.config.sources['machine_description']} belongs to {machine['serial']}"
        )
    version = handle.software["version"]
    if version not in machine["tested_versions"]:
        message = (
            f"{handle.software['software']} {version} has not been tested with this driver "
            f"(tested: {machine['tested_versions']}); watch the first commands closely"
        )
        logger.warning(message)
        handle.log.record("warning", message)


def disconnect(handle: MockHandle) -> None:
    """Close the session. Every later call raises; a second disconnect is harmless."""
    if handle.closed:
        return
    handle.closed = True
    handle.vendor.close()


# --- describing the setup -----------------------------------------------------

# The microscope in plain words, for whoever drives it: a person, a notebook, or
# the ZMART AI agent, which builds its picture of the instrument from this. It
# says what the other answers cannot: what each setting means, in which unit and
# within which bounds, and which objective sits in which slot. Travel ranges and
# routines are left to get_xyz and get_procedures, which report them live. The
# bounds of the settings come from this microscope's limits file when get_info
# runs, so the description never promises more than the driver allows.
DESCRIPTION = """A pretend widefield fluorescence microscope that runs entirely in software (MockScope Control), for trying workflows without hardware. It images a sample of scattered fluorescent spots on a slide that is slightly tilted, so the sharp height changes a little from place to place.

Stage: x and y move the slide, z moves the focus, all in micrometres from the origin. z has two motors: "motoric" for long moves and "piezo" for fine, fast steps around the current height.

Objectives, by slot: 1 is 10x/0.30 Air (1.0 um per pixel), 2 is 20x/0.75 Air (0.5 um per pixel), 3 is 40x/0.95 Air (0.25 um per pixel). Every image is 64 x 64 pixels, so the field of view shrinks as the magnification grows. Changing objective shifts the view slightly; the driver corrects for it.

Settings (the changeable part of the state): objective is the slot number above; laser_power is the excitation in percent, {laser_power}; gain is the detector gain, {gain}; exposure_ms is the exposure time in milliseconds, {exposure_ms}. The image gets brighter with more laser power, gain or exposure; very bright settings saturate it.

Acquiring saves each image under the output folder, in a folder named by the acquisition type and a file named by the position label. A z-stack of several planes around the current height is one acquisition."""


def _described(limits: dict) -> str:
    """The description, with each setting's bounds as this microscope's limits set them."""
    bounds = {name: f"{low:g} to {high:g}" for name, (low, high) in limits["settings"].items()}
    return DESCRIPTION.format(**bounds)


def get_info(handle: MockHandle) -> dict:
    """Where images go, a description of the microscope, and the configuration in use."""
    _require_open(handle)
    return _answer(
        {
            "output_root": str(handle.output_root),
            "description": _described(handle.config.limits),
            "client": handle.client,
            "serial": handle.config.machine_description["serial"],
            "software": dict(handle.software),
            "configuration": dict(handle.config.sources),
        }
    )


def get_actuators(handle: MockHandle) -> dict:
    """The motors that can move each axis."""
    _require_open(handle)
    return _answer({axis: list(names) for axis, names in get.ACTUATORS.items()})


def _actuators(with_actuators: dict | None) -> dict[str, str]:
    """The motor per axis: the one named, or the first in the list. Never sticky."""
    chosen = {axis: names[0] for axis, names in get.ACTUATORS.items()}
    for axis, name in (with_actuators or {}).items():
        if axis not in get.ACTUATORS or name not in get.ACTUATORS[axis]:
            raise ValueError(f"unknown actuator {name!r} for axis {axis!r}")
        chosen[axis] = name
    return chosen


# --- moving -------------------------------------------------------------------


def get_xyz(handle: MockHandle, *, with_actuators: dict | None = None) -> dict:
    """The position in micrometers from the origin, how far each axis may travel,
    and how far a picture can reach along it."""
    _require_open(handle)
    chosen = _actuators(with_actuators)
    raw = get.raw_position(handle).value_or_raise("the position")
    user = get.user_position(handle).value_or_raise("the position")
    ranges = user_range(handle.config, raw["objective"])
    reaches = _reach(handle, ranges)
    return _answer(
        {
            axis: {
                "value": user[axis],
                "actuator": chosen[axis],
                "unit": "um",
                "range": ranges[axis],
                "reach": reaches[axis],
            }
            for axis in ("x", "y", "z")
        }
    )


def _reach(handle: MockHandle, ranges: dict[str, list[float]]) -> dict[str, list[float]]:
    """Everywhere a picture can show, per axis: the travel widened by half the widest field.

    A picture is centred on the stage position, so one taken at the edge of
    travel shows half a field beyond it. The widest field belongs to the
    objective with the largest pixels among those the limits allow; its
    longest side is used for x and y alike, so a turned camera is covered
    too. z is not widened: this microscope's z-stacks go upwards from the
    stage height and the limits keep the whole stack inside the travel, so
    no plane is ever taken outside it.
    """
    pixel_sizes = handle.config.image_stage_registration["pixel_size_um"]
    widest_pixel = max(float(pixel_sizes[str(slot)]) for slot in handle.config.limits["objectives"])
    half_field = max(handle.camera["width"], handle.camera["height"]) * widest_pixel / 2
    widen = {"x": half_field, "y": half_field, "z": 0.0}
    return {axis: [low - widen[axis], high + widen[axis]] for axis, (low, high) in ranges.items()}


def set_xyz(
    handle: MockHandle, x: float, y: float, z: float, *, with_actuators: dict | None = None
) -> dict:
    """Move to a position in micrometers from the origin, and confirm it.

    Raises ``ValueError`` for a position outside the limits or an unknown
    motor, and ``RuntimeError`` when the move cannot be confirmed: carrying
    on at an unknown position is never safe.
    """
    _require_open(handle)
    chosen = _actuators(with_actuators)
    outcome, _raw = setter.move_to_user(handle, x=x, y=y, z=z, z_actuator=chosen["z"])
    if not outcome.confirmed:
        raise RuntimeError(f"the move to ({x}, {y}, {z}) could not be confirmed: {outcome.reason}")
    reached = get.user_position(handle).value_or_raise("the position")
    return _answer({"position": {"x": x, "y": y, "z": z}, "readback": reached, "actuators": chosen})


# --- state --------------------------------------------------------------------


def get_state(handle: MockHandle) -> dict:
    """The settings that can be changed, and a read-only description of the instrument."""
    _require_open(handle)
    changeable = get.state(handle).value_or_raise("the settings")
    slot = str(changeable["objective"])
    hardware = get.hardware(handle).value_or_raise("the hardware description")
    pixel = float(handle.config.image_stage_registration["pixel_size_um"].get(slot, 0.0))
    camera = hardware["camera"]
    return _answer(
        {
            "changeable": changeable,
            "observed": {
                "serial": hardware["serial"],
                "objective": hardware["objectives"][int(slot)]["name"],
                "pixel_size": {"x": pixel, "y": pixel, "unit": "um"},
                "frame_size": {
                    "x": camera["width"] * pixel,
                    "y": camera["height"] * pixel,
                    "unit": "um",
                },
                "software": dict(handle.software),
            },
        }
    )


def set_state(handle: MockHandle, state: dict) -> dict:
    """Apply the ``changeable`` settings, confirm each one, and report what happened.

    ``observed`` is never read. Settings this microscope does not know are
    listed under ``ignored``. ``success`` is False when nothing was applied,
    or when a setting was sent but could not be confirmed; both are safe to
    carry on from, so they are reported, not raised.
    """
    _require_open(handle)
    changeable = dict(state.get("changeable", {}))
    applied: dict[str, Any] = {}
    unconfirmed: dict[str, str] = {}
    for name in _STATE_ORDER:
        if name not in changeable:
            continue
        value = changeable[name]
        if name == "objective":
            outcome = setter.set_objective(handle, value)
        else:
            outcome = setter.set_setting(handle, name, value)
        if outcome.confirmed:
            applied[name] = value
        else:
            unconfirmed[name] = outcome.reason
    ignored = sorted(set(changeable) - set(_STATE_ORDER))
    success = bool(applied) and not unconfirmed
    content = {"applied": applied, "unconfirmed": unconfirmed, "ignored": ignored}
    return _answer(content, success=success)


# --- acquiring ----------------------------------------------------------------


def _menu() -> dict:
    return {
        "folder": {"options": "any text; empty saves straight into output_root", "active": ""},
        "backlash_correction": {"options": [True, False], "active": True},
        "format": {"options": list(FORMATS), "active": "ome-tiff"},
        "z_planes": {"options": "whole number from 1 up to the limit", "active": 1},
        "z_step_um": {"options": "number > 0", "active": 1.0},
    }


def get_acquisition_settings(handle: MockHandle) -> dict:
    """The choices for capturing and saving, with allowed values and the active one."""
    _require_open(handle)
    return _answer(_menu())


def _with_defaults(settings: dict | None) -> dict:
    """Check the settings against the menu and fill in the ones left out."""
    menu = _menu()
    resolved = {name: spec["active"] for name, spec in menu.items()}
    for name, value in (settings or {}).items():
        if name not in menu:
            raise ValueError(f"unknown acquisition setting {name!r}")
        allowed = menu[name]["options"]
        if isinstance(allowed, list) and value not in allowed:
            raise ValueError(f"invalid value {value!r} for acquisition setting {name!r}")
        resolved[name] = value
    if not isinstance(resolved["folder"], str):
        raise ValueError(f"acquisition setting 'folder' must be text, not {resolved['folder']!r}")
    planes = resolved["z_planes"]
    if isinstance(planes, bool) or not isinstance(planes, int) or planes < 1:
        raise ValueError(f"invalid value {planes!r} for acquisition setting 'z_planes'")
    step = resolved["z_step_um"]
    if isinstance(step, bool) or not isinstance(step, (int, float)) or not step > 0:
        raise ValueError(f"invalid value {step!r} for acquisition setting 'z_step_um'")
    return resolved


def acquire(
    handle: MockHandle, *, position_label: str, acquisition_settings: dict | None = None
) -> dict:
    """Capture an image (or a z-stack) here and save it, in one step.

    The files are named after ``position_label``. Settings left out keep their
    active value; ``folder`` puts the files in a folder of that name. The content lists every saved
    file under ``files`` (the images, then the ``command_log`` that records
    how they were made, which is also named on its own), and under ``planes``
    which file, channel and depth each image plane is and the stage position
    it was taken at. When the acquisition cannot be confirmed, ``success`` is
    False and no files or planes are listed.
    """
    _require_open(handle)
    settings = _with_defaults(acquisition_settings)
    mark = handle.log.mark()
    if settings["backlash_correction"]:
        PROCEDURES["backlash_takeup"]["run"](handle)
    position = get.user_position(handle).value_or_raise("the position")
    # The vendor software takes short names only; the saved files keep the full label.
    vendor_name = safe_name(f"{settings['folder']}_{position_label}")[:NAME_LIMIT]
    outcome = setter.acquire(
        handle, name=vendor_name, z_planes=settings["z_planes"], z_step_um=settings["z_step_um"]
    )
    content: dict[str, Any] = {
        "position_label": position_label,
        "folder": settings["folder"],
        "format": settings["format"],
        "settle": "backlash-corrected" if settings["backlash_correction"] else "direct",
        "position": position,
        "confirmed": outcome.confirmed,
    }
    if not outcome.confirmed:
        return _answer(
            {**content, "files": [], "planes": [], "reason": outcome.reason}, success=False
        )
    saved = save_acquisition(
        handle,
        vendor_file=outcome.result,
        folder=settings["folder"],
        position_label=position_label,
        image_format=settings["format"],
        position_um=position,
        log_mark=mark,
    )
    return _answer({**content, **saved, "vendor_file": outcome.result})


# --- procedures ---------------------------------------------------------------


def get_procedures(handle: MockHandle) -> dict:
    """The routines this microscope offers, each with a plain description."""
    _require_open(handle)
    return _answer(
        {name: {"description": spec["description"]} for name, spec in PROCEDURES.items()}
    )


def run_procedure(handle: MockHandle, procedure: dict) -> dict:
    """Run one routine by name; any other entries are passed to it. An unknown name is refused."""
    _require_open(handle)
    entries = dict(procedure)
    name = entries.pop("name", None)
    if name not in PROCEDURES:
        raise ValueError(f"unknown procedure {name!r}")
    run = PROCEDURES[name]["run"]
    try:
        inspect.signature(run).bind(handle, **entries)
    except TypeError as exc:
        raise ValueError(f"procedure {name!r} does not take these entries: {exc}") from None
    return _answer({"ran": name, **run(handle, **entries)})
