"""The mock microscope driver: a complete ZMART driver for a pretend microscope.

It is built from the same parts as every ZMART driver (see the driver
anatomy in ``docs/1_plug_in_a_driver/README.md``), on top of MockScope Control, pretend vendor
software in ``testing/mock_api``. Read it as the template for a new driver,
and use it to try workflows without hardware. Plug it in with::

    zmart_controller.set_instrument(zmart_controller.mock)

The functions the controller calls, one per command, are in ``driver.py`` and
are listed here, which is how the controller finds them.
"""

from .driver import (
    acquire,
    connect,
    disconnect,
    get_acquisition_settings,
    get_actuators,
    get_info,
    get_procedures,
    get_state,
    get_xyz,
    run_procedure,
    set_state,
    set_xyz,
)

__all__ = [
    "acquire",
    "connect",
    "disconnect",
    "get_acquisition_settings",
    "get_actuators",
    "get_info",
    "get_procedures",
    "get_state",
    "get_xyz",
    "run_procedure",
    "set_state",
    "set_xyz",
]
