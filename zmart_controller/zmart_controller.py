"""The ZmartController: one microscope, one method per command.

Make one with a driver, and it connects::

    mic = ZmartController(ZmartDriver, connection)   # while writing a driver
    mic = ZmartController("my-scope")                # once installed
    mic.set_xyz(100, 50, 0)

Each method calls the method of the same name on the ``ZmartDriver``, which
hands back ``True`` and the values, or ``False`` and a message. There are
three outcomes, and the answer always has the same shape:

- success: ``{"success": True, "content": ...}`` with the values;
- failure, the driver says the microscope did not do it:
  ``{"success": False, "content": "..."}`` with the driver's message;
- call failure, the method itself raised: the same, with the error text.

Every call returns when the driver has finished.

A driver may also be a module with one function per command, such as the
mock; its functions already build the answers themselves.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

from functools import partial
from typing import Any


class ZmartController:
    """One connected microscope. ``context`` names the driver: ``{"driver": ...}``."""

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
        self.context = {"driver": name or driver_name(driver)}

        driver_class = driver if isinstance(driver, type) else getattr(driver, "ZmartDriver", None)
        if driver_class is not None:
            self._handle = driver_class(connection)  # making it connects
            return
        # An older driver, a module with one function per command: its
        # functions answer directly, so they stand in for the methods below.
        functions = driver_functions(driver)
        self._handle = functions.pop("connect")(connection)
        for command, function in functions.items():
            setattr(self, command, partial(function, self._handle))

    def disconnect(self) -> None:
        """Close the connection, if the driver has a way to close it."""
        if hasattr(self._handle, "disconnect"):
            self._handle.disconnect()

    def get_info(self) -> dict:
        """Where images are saved, and the microscope in plain words."""
        try:
            ok, result = self._handle.get_info()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        output_root, description = result

        return {
            "success": True,
            "content": {"output_root": output_root, "description": description},
        }

    def get_actuators(self) -> dict:
        """The motors that can move each axis, e.g. ``{"z": ["motoric", "piezo"]}``."""
        try:
            ok, result = self._handle.get_actuators()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        x_motors, y_motors, z_motors = result

        return {"success": True, "content": {"x": x_motors, "y": y_motors, "z": z_motors}}

    def get_xyz(self, with_actuators: dict | None = None) -> dict:
        """Each axis: its position in micrometres from the origin, the motor read, and the canvas."""
        try:
            ok, result = self._handle.get_xyz(with_actuators)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        x, y, z, x_motor, y_motor, z_motor, canvas = result
        x_min, x_max, y_min, y_max, z_min, z_max = canvas

        return {
            "success": True,
            "content": {
                "x": {"value": x, "actuator": x_motor, "canvas": [x_min, x_max]},
                "y": {"value": y, "actuator": y_motor, "canvas": [y_min, y_max]},
                "z": {"value": z, "actuator": z_motor, "canvas": [z_min, z_max]},
            },
        }

    def set_xyz(self, x: float, y: float, z: float, with_actuators: dict | None = None) -> dict:
        """Move to a position in micrometres from the origin; ``with_actuators`` picks the motor per axis."""
        try:
            ok, result = self._handle.set_xyz(x, y, z, with_actuators)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        x_motor, y_motor, z_motor = result

        return {
            "success": True,
            "content": {
                "position": {"x": x, "y": y, "z": z},
                "actuators": {"x": x_motor, "y": y_motor, "z": z_motor},
            },
        }

    def get_state(self) -> dict:
        """The settings: ``changeable``, which ``set_state`` applies, and ``observed``, read-only."""
        try:
            ok, result = self._handle.get_state()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        changeable, observed = result

        return {"success": True, "content": {"changeable": changeable, "observed": observed}}

    def set_state(self, state: dict) -> dict:
        """Apply the settings under ``changeable``; the answer names what was applied."""
        try:
            ok, result = self._handle.set_state(state["changeable"])

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        applied = result

        return {"success": True, "content": {"applied": applied}}

    def get_acquisition_settings(self) -> dict:
        """The choices for one acquisition: ``{name: {"options": [...], "active": value}}``."""
        try:
            ok, result = self._handle.get_acquisition_settings()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        settings = result

        return {"success": True, "content": settings}

    def acquire(self, position_label: str, acquisition_settings: dict | None = None) -> dict:
        """Capture an image here and save it; the answer lists every file and image plane."""
        try:
            ok, result = self._handle.acquire(position_label, acquisition_settings)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        files, planes = result

        return {
            "success": True,
            "content": {"position_label": position_label, "files": files, "planes": planes},
        }

    def get_procedures(self) -> dict:
        """The routines the microscope offers: ``{name: {"description": ...}}``."""
        try:
            ok, result = self._handle.get_procedures()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        procedures = result

        return {"success": True, "content": procedures}

    def run_procedure(self, procedure: dict) -> dict:
        """Run the routine named by ``procedure["name"]``; the other keys are its arguments."""
        try:
            ok, result = self._handle.run_procedure(procedure)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        ran = result

        return {"success": True, "content": {"ran": ran}}


#: The commands: the public methods of the controller. A ZmartDriver has a
#: method for each, a module driver a function. disconnect is optional.
COMMANDS = tuple(name for name in vars(ZmartController) if not name.startswith("_"))
