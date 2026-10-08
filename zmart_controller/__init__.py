"""ZMART Controller: one small, universal way to drive any microscope.

Plug in a driver, then drive the microscope through the module itself::

    import zmart_controller

    zmart_controller.get_drivers()            # ["mock", ...]: the drivers installed here
    zmart_controller.get_instruments()        # the same, with how each one connects
    zmart_controller.set_instrument("mock")   # the simulated microscope
    zmart_controller.set_xyz(10, 20, 5)
    zmart_controller.acquire(position_label="A1")
    zmart_controller.disconnect()

A driver is the whole set of files that talks to one microscope; towards the
controller it offers one function per command. Register a driver's folder on
the computer once, then plug it in by name::

    zmart_controller.register_driver("path/to/zmart_controller_plugin.py")
    zmart_controller.set_instrument("stellaris")

To drive several microscopes at once, hold a session for each::

    from zmart_controller.session import set_instrument

    mic_a = set_instrument(driver_a)
    mic_b = set_instrument(driver_b, {"host": "scope-b"})
    mic_a.acquire(position_label="A1")

Two cautions for the short way. Call through the module each time, as in
``zmart_controller.set_xyz(...)``; a command saved in a variable keeps pointing
at the old microscope after a switch. And it assumes that one thread drives the
microscope (a thread is one line of execution in a program; most scripts have
just one). A program that drives microscopes from several threads holds a
session for each.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

__version__ = "0.1.0"
__author__ = "Thom de Hoog"
__email__ = "thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com"
__affiliation__ = "Center for Microscopy and Image Analysis (ZMB), University of Zurich"

from .session import Session
from .session import set_instrument as _set_instrument
from .utils import (
    check_acquire_answer,
    get_drivers,
    get_instruments,
    register_driver,
    remove_driver,
    validate_driver,
)

__all__ = [
    "Session",
    "get_drivers",
    "get_instruments",
    "register_driver",
    "remove_driver",
    "check_acquire_answer",
    "validate_driver",
    "disconnect",
    "set_instrument",
]

# The one active microscope that the module-level commands go to.
_active: Session | None = None


def set_instrument(driver, connection=None) -> Session:
    """Plug in a driver, connect to its microscope, and make it the active one.

    ``driver`` is the name of a registered driver, from :func:`get_drivers`,
    or a module with one function per command, such as
    ``zmart_controller.mock``; ``connection`` is handed to its ``connect``.
    Module-level commands then go to it. The previously active microscope is
    disconnected. Returns the :class:`Session` as well, for those who want to
    hold it.
    """
    global _active
    new = _set_instrument(driver, connection)
    # Connect the new one first, so a failed connect never loses a working
    # session. Record it before closing the old one, so it is never lost if
    # closing raises.
    previous, _active = _active, new
    if previous is not None and previous is not new:
        previous.disconnect()
    return new


def disconnect() -> None:
    """Disconnect the active microscope.

    Module-level commands then raise until :func:`set_instrument` picks a new
    one. With no active microscope this does nothing.
    """
    global _active
    previous, _active = _active, None
    if previous is not None:
        previous.disconnect()


def __getattr__(name: str):
    # The mock driver is loaded only when asked for, so importing the
    # controller stays light.
    if name == "mock":
        import importlib

        return importlib.import_module(".mock", __name__)
    # Send commands such as acquire or set_xyz to the active microscope.
    if _active is not None and hasattr(_active, name):
        return getattr(_active, name)
    if _active is None and not name.startswith("_"):
        raise AttributeError(
            f"no active microscope - call set_instrument(...) before zmart_controller.{name}(...)"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
