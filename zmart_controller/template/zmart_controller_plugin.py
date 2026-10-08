"""A ZMART driver to copy: the file the controller plugs into.

Copy the whole ``template`` folder, give it a name, and fill in ``scope.py``.
This file stays as it is. It gives the controller the twelve functions it
looks for, and each one does the same two things: call the function of the
same name in ``scope.py``, and wrap what comes back in the answer shape
every command shares, ``{"success": ..., "content": ...}``.

``docs/1_plug_in_a_driver/README.md`` explains every key in the answers.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from . import scope  # scope.py, in this folder: the code that talks to the vendor software

NAME = "my-scope"  # the driver's name in the controller's list

CONNECTION = {  # how to reach this microscope; get_instruments() shows it
    "microscope": "my-scope-01",  # which instrument this is
    "api_type": "socket",  # how the vendor software is reached
    "host": "127.0.0.1",  # where it listens
    "password": "",  # never shown by get_instruments()
    "config": "C:/my-scope/config.ini",
    "output_root": "D:/images",  # where images are saved
}


def connect(connection):

    handle = scope.connect(connection)

    return handle  # any object that holds the live connection


def disconnect(handle):  # optional

    scope.disconnect(handle)

    return None


def get_info(handle):

    output_root, description = scope.get_info(handle)

    return {"success": True, "content": {"output_root": output_root, "description": description}}


def get_actuators(handle):

    x_motors, y_motors, z_motors = scope.get_actuators(handle)

    return {"success": True, "content": {"x": x_motors, "y": y_motors, "z": z_motors}}


def get_xyz(handle, *, with_actuators=None):

    x, y, z, x_motor, y_motor, z_motor = scope.get_xyz(handle, with_actuators)
    x_min, x_max, y_min, y_max, z_min, z_max = scope.get_canvas(handle)

    return {
        "success": True,
        "content": {
            "x": {"value": x, "actuator": x_motor, "canvas": [x_min, x_max]},
            "y": {"value": y, "actuator": y_motor, "canvas": [y_min, y_max]},
            "z": {"value": z, "actuator": z_motor, "canvas": [z_min, z_max]},
        },
    }


def set_xyz(handle, x, y, z, *, with_actuators=None):

    x_motor, y_motor, z_motor = scope.set_xyz(handle, x, y, z, with_actuators)

    return {
        "success": True,
        "content": {
            "position": {"x": x, "y": y, "z": z},
            "actuators": {"x": x_motor, "y": y_motor, "z": z_motor},
        },
    }


def get_state(handle):

    changeable, observed = scope.get_state(handle)

    return {"success": True, "content": {"changeable": changeable, "observed": observed}}


def set_state(handle, state):

    applied = scope.set_state(handle, state["changeable"])

    return {"success": True, "content": {"applied": applied}}


def get_acquisition_settings(handle):

    settings = scope.get_acquisition_settings(handle)  # {name: {"options": [...], "active": value}}

    return {"success": True, "content": settings}


def acquire(handle, *, position_label, acquisition_settings=None):

    files, planes = scope.acquire(handle, position_label, acquisition_settings)

    return {
        "success": True,
        "content": {
            "position_label": position_label,
            "files": files,  # the path of every file saved
            "planes": planes,  # [{"path", "c", "z", "t", "x_um", "y_um", "z_um"}, ...]
        },
    }


def get_procedures(handle):

    procedures = scope.get_procedures(handle)  # {name: {"description": ...}}

    return {"success": True, "content": procedures}


def run_procedure(handle, procedure):

    scope.run_procedure(handle, procedure)

    return {"success": True, "content": {"ran": procedure["name"]}}
