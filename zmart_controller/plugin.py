"""The plugin: how a driver made of a ``ZmartDriver`` class is plugged into the controller.

A driver is two files: ``zmart_driver.json``, the driver's name, where its
class file is, and how to reach the microscope, and that class file,
``zmart_driver.py`` by default, with a ``ZmartDriver`` class that has one
method per command. This module is the same for every such
driver, so it lives here rather than in each driver's folder.

:func:`load` reads the two files and returns the driver as the controller
expects it: one function per command, found by name. ``connect`` makes one
``ZmartDriver`` from the connection and returns it as the handle. Every other
function below calls the method of the same name on the handle and wraps
what comes back in the shape every command shares,
``{"success": True, "content": ...}``. A method that raises
:class:`NotConfirmed` answers ``success: False`` instead, with the reason;
any other exception is passed on to the workflow unchanged.
``docs/1_plug_in_a_driver/README.md`` explains every key in the answers.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class NotConfirmed(Exception):
    """Raise this from a ``ZmartDriver`` method for a soft failure: the command was
    sent, but what it asked for never showed up, and it is safe to carry on.

    The controller answers ``{"success": False, "content": error_text}``,
    where ``error_text`` is the message given here. Never raise it from
    ``set_xyz``: carrying on at an unknown position is not safe, so a move
    that cannot be confirmed raises ``RuntimeError``.
    """


def _soft_outcomes(function):
    """Let a plugin function answer ``success: False`` when the method raises NotConfirmed."""

    def answering(handle, *args, **kwargs):
        try:
            return function(handle, *args, **kwargs)
        except NotConfirmed as failure:
            return {"success": False, "content": str(failure)}

    answering.__name__ = function.__name__
    answering.__doc__ = function.__doc__
    return answering


#: The settings file a driver is installed from, and the class file it names by default.
SETTINGS_FILE = "zmart_driver.json"
DRIVER_FILE = "zmart_driver.py"


def load(where: str | Path) -> SimpleNamespace:
    """The driver in the folder ``where``, or at that ``zmart_driver.json``, ready to plug in.

    Reads the name, the connection and the class file's path from
    ``zmart_driver.json`` (``driver``, relative to the JSON's folder,
    ``zmart_driver.py`` when left out), imports the ``ZmartDriver`` class
    from that file, and returns
    an object with ``NAME``, ``CONNECTION`` and one function per command,
    which ``set_instrument``, ``validate_driver`` and ``register_driver``
    all accept. Raises ``ValueError`` naming what is missing.
    """
    from .utils import _FILE_PREFIX, _import

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
    return functions_for(driver_class, name, connection)


def functions_for(driver_class: type, name: str, connection: dict[str, Any]) -> SimpleNamespace:
    """The twelve plugin functions for ``driver_class``, as one object the controller accepts."""

    def connect(connection):
        handle = driver_class(connection)

        return handle  # the connected driver; every other function receives it back

    return SimpleNamespace(
        __name__=name,
        NAME=name,
        CONNECTION=dict(connection),
        connect=connect,
        disconnect=disconnect,
        get_info=get_info,
        get_actuators=get_actuators,
        get_xyz=get_xyz,
        set_xyz=set_xyz,
        get_state=get_state,
        set_state=set_state,
        get_acquisition_settings=get_acquisition_settings,
        acquire=acquire,
        get_procedures=get_procedures,
        run_procedure=run_procedure,
    )


def disconnect(handle):  # optional

    handle.disconnect()

    return None


@_soft_outcomes
def get_info(handle):

    output_root, description = handle.get_info()

    return {"success": True, "content": {"output_root": output_root, "description": description}}


@_soft_outcomes
def get_actuators(handle):

    x_motors, y_motors, z_motors = handle.get_actuators()

    return {"success": True, "content": {"x": x_motors, "y": y_motors, "z": z_motors}}


@_soft_outcomes
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


@_soft_outcomes
def set_xyz(handle, x, y, z, *, with_actuators=None):

    x_motor, y_motor, z_motor = handle.set_xyz(x, y, z, with_actuators)

    return {
        "success": True,
        "content": {
            "position": {"x": x, "y": y, "z": z},
            "actuators": {"x": x_motor, "y": y_motor, "z": z_motor},
        },
    }


@_soft_outcomes
def get_state(handle):

    changeable, observed = handle.get_state()

    return {"success": True, "content": {"changeable": changeable, "observed": observed}}


@_soft_outcomes
def set_state(handle, state):

    applied = handle.set_state(state["changeable"])

    return {"success": True, "content": {"applied": applied}}


@_soft_outcomes
def get_acquisition_settings(handle):

    settings = handle.get_acquisition_settings()  # {name: {"options": [...], "active": value}}

    return {"success": True, "content": settings}


@_soft_outcomes
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


@_soft_outcomes
def get_procedures(handle):

    procedures = handle.get_procedures()  # {name: {"description": ...}}

    return {"success": True, "content": procedures}


@_soft_outcomes
def run_procedure(handle, procedure):

    handle.run_procedure(procedure)

    return {"success": True, "content": {"ran": procedure["name"]}}
