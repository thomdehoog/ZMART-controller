"""The Session: one method per command, each calling the driver.

The controller does no microscope work. Each method hands the call to the
driver and returns the driver's answer unchanged. Every check belongs to the
driver, including whether the connection is still open.

Every call is synchronous. It returns when the driver has finished.

Every command answers with ``{"success": bool, "content": ...}``. ``success``
says whether the driver did what was asked. ``content`` is the driver's own
content. A soft outcome, one that is safe to carry on from, comes back as
``success: False``. Anything unsafe to carry on from is raised instead:
``ValueError`` for a mistake in the request, ``RuntimeError`` for a failure on
the microscope.

Configuration lives in the driver. The origin, the travel limits and the
calibration are saved by the driver's own setup step and loaded at connect.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

from typing import Any

from .utils import driver_functions, driver_name, find_driver


class Session:
    """A connected microscope, returned by :func:`set_instrument`.

    Each method calls the matching driver function and returns its answer.
    The session keeps no state and refuses nothing. Its one public attribute,
    ``context``, names the driver that was plugged in: ``{"driver": ...}``.
    """

    def __init__(
        self,
        ops: dict[str, Any],
        handle: Any,
        context: dict[str, str],
    ) -> None:
        self._ops = ops  # command name -> driver function
        self._handle = handle  # the driver's own connection object

        self.context = context

    # --- state and procedures ------------------------------------------------

    def get_state(self) -> dict:
        """Capture the instrument's settings so they can be applied again later.

        The ``content`` has two parts. ``"changeable"`` holds the settings that
        :meth:`set_state` applies. ``"observed"`` is a read-only description of
        the instrument. The controller does not look inside either.
        """
        return self._ops["get_state"](self._handle)

    def set_state(self, state: dict) -> dict:
        """Apply a state captured with :meth:`get_state` (pass its ``content``).

        The driver applies the ``"changeable"`` part only. ``"observed"`` is
        never an instruction.
        """
        return self._ops["set_state"](self._handle, state)

    def get_procedures(self) -> dict:
        """The routines this microscope offers, such as autofocus."""
        return self._ops["get_procedures"](self._handle)

    def run_procedure(self, procedure: dict) -> dict:
        """Run one routine from :meth:`get_procedures`, chosen by ``{"name": ...}``."""
        return self._ops["run_procedure"](self._handle, procedure)

    # --- movement -----------------------------------------------------------

    def get_actuators(self) -> dict:
        """The motors that can move each axis, e.g. ``{"z": ["motoric", "piezo"]}``.

        Pick one per axis with ``with_actuators`` on :meth:`get_xyz` and
        :meth:`set_xyz`.
        """
        return self._ops["get_actuators"](self._handle)

    def get_xyz(self, with_actuators: dict | None = None) -> dict:
        """Read each axis: its position, and how far it can travel.

        Both in micrometres from the origin. ``with_actuators`` names a motor
        per axis, e.g. ``{"z": "piezo"}``. The names come from
        :meth:`get_actuators`; the driver checks them.
        """
        return self._ops["get_xyz"](self._handle, with_actuators=with_actuators)

    def set_xyz(self, x: float, y: float, z: float, with_actuators: dict | None = None) -> dict:
        """Move to a position, in micrometres from the origin.

        ``with_actuators`` names the motor to use per axis. Left out, the
        driver uses its default. Any calibration is the driver's job.
        """
        return self._ops["set_xyz"](self._handle, x, y, z, with_actuators=with_actuators)

    # --- acquire ---------------------------------------------------------------

    def get_acquisition_settings(self) -> dict:
        """The choices for capturing and saving, with allowed values and the active one.

        Asked of the driver afresh on every call.
        """
        return self._ops["get_acquisition_settings"](self._handle)

    def acquire(self, position_label: str, acquisition_settings: dict | None = None) -> dict:
        """Capture an image here and save it, in one step.

        ``position_label`` names this position in the saved files, e.g.
        ``"A1"``. ``acquisition_settings`` holds choices from :meth:`get_acquisition_settings`;
        any left out keep their active value. The content lists every saved file
        under ``files``, so a workflow finds its pictures the same way on every
        microscope.
        """
        return self._ops["acquire"](
            self._handle, position_label=position_label, acquisition_settings=acquisition_settings
        )

    # --- information and lifecycle --------------------------------------------

    def get_info(self) -> dict:
        """Describe the connected setup.

        Every driver reports ``output_root``, the folder where images are
        saved. Anything else is an extra of that driver, and a workflow meant
        for any microscope should not rely on it.
        """
        return self._ops["get_info"](self._handle)

    def disconnect(self) -> None:
        """Close the connection, if the driver has a way to close it."""
        disconnect = self._ops.get("disconnect")
        if disconnect is not None:
            disconnect(self._handle)


def set_instrument(driver: Any, connection: dict[str, Any] | None = None) -> Session:
    """Plug in a driver, connect to its microscope, and return the :class:`Session`.

    ``driver`` is the name of a registered driver, from ``get_drivers()``, or
    the driver itself: a module such as ``zmart_controller.mock``, or a dict
    from command name to function. ``connection`` is handed to the driver's
    ``connect`` unchanged; it holds whatever that driver needs, such as a host
    name. Left out, the driver's own ``CONNECTION`` is used, if it has one.
    Raises ``ValueError`` naming any function the driver is missing.
    """
    name = None
    if isinstance(driver, str):
        name = driver
        driver, saved = find_driver(name)
        connection = saved if connection is None else connection
    elif connection is None:
        connection = getattr(driver, "CONNECTION", None)
    ops = driver_functions(driver)
    handle = ops["connect"](dict(connection or {}))
    return Session(ops, handle, {"driver": name or driver_name(driver)})
