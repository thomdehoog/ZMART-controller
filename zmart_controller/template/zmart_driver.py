"""The code that talks to your microscope's vendor software. Fill in every method.

The controller creates one ``ZmartDriver`` when it connects and calls the
method of the same name for every command. Each method hands back a pair:
``True`` and the values when the microscope did what was asked, or
``False`` and a message when it did not. The controller turns that into the
answer the workflow sees. A method that raises is reported with the error
text, so raise ``ValueError`` for a request that is wrong, such as a
position outside the travel or an unknown setting.

Positions are micrometres from the origin, the saved zero point of this
microscope. In a saved image, right is +x and down is +y. Every method
below raises ``NotImplementedError`` until you write it, so
``validate_driver`` tells you what is still missing.
"""


class ZmartDriver:
    """One connected microscope: the vendor connection and everything to drive it."""

    def __init__(self, connection):
        """Open the connection to the vendor software and keep what you need on ``self``.

        ``connection`` is the dictionary from ``zmart_driver.json``: which
        microscope, how its software is reached, where it listens, its
        password, and its configuration file.
        """
        raise NotImplementedError("ZmartDriver.__init__: open the connection")

    def disconnect(self):
        """Close the connection to the vendor software."""
        raise NotImplementedError("ZmartDriver.disconnect: close the connection")

    def get_info(self):
        """Return ``True, description``: the microscope in plain words.

        Say what each changeable setting means, its unit and bounds, which
        objective sits in which slot, and which way +z points.
        """
        raise NotImplementedError("ZmartDriver.get_info: return True, description")

    def get_actuators(self):
        """Return ``True, (x_motors, y_motors, z_motors)``: the motor names per axis, at least one each."""
        raise NotImplementedError(
            "ZmartDriver.get_actuators: return True, (x_motors, y_motors, z_motors)"
        )

    def get_xyz(self, with_actuators):
        """Return ``True, (x, y, z, actuators, canvas)``, everything in micrometres.

        ``x``, ``y`` and ``z`` are the position from the origin, in the
        sample's coordinate system. ``actuators`` is
        ``{"x": {...}, "y": {...}, "z": {...}}``: for each axis, every motor
        ``get_actuators`` lists with its own raw reading, exactly as the
        microscope reports it and without any origin subtracted, for example
        ``{"z": {"motoric": 48211.5, "piezo": 37.0}}``. ``canvas`` is
        ``(x_min, x_max, y_min, y_max, z_min, z_max)``: the travel widened
        by half a field of view, everywhere a picture can show.
        ``with_actuators`` picks a motor per axis, such as ``{"z": "piezo"}``,
        or is None for the first one; raise ``ValueError`` for a name that
        is not listed.
        """
        raise NotImplementedError("ZmartDriver.get_xyz: return True, (x, y, z, actuators, canvas)")

    def set_xyz(self, x, y, z, with_actuators):
        """Move the stage, then return what ``get_xyz`` returns, or ``False, message``.

        Raise ``ValueError`` for a position outside the travel. Read the
        position back until the stage has arrived, then hand back the same
        ``True, (x, y, z, actuators, canvas)`` as ``get_xyz``, read from the
        microscope, so the workflow sees where the stage really is. When the
        stage never arrives, return ``False`` and say where it is, so the
        workflow can stop.
        """
        raise NotImplementedError("ZmartDriver.set_xyz: move, then return what get_xyz returns")

    def get_state(self):
        """Return ``True, (changeable, observed)``: two dictionaries.

        ``changeable`` holds the settings ``set_state`` applies, such as
        exposure time. ``observed`` holds what can only be read, such as the
        objective in place.
        """
        raise NotImplementedError("ZmartDriver.get_state: return True, (changeable, observed)")

    def set_state(self, changeable):
        """Apply each setting and return ``True, applied``, or ``False, message``.

        Raise ``ValueError`` for a setting the microscope does not have. Read
        each setting back; when one did not take, return ``False`` and say
        which.
        """
        raise NotImplementedError("ZmartDriver.set_state: apply the settings, return True, applied")

    def get_acquisition_settings(self):
        """Return ``True, settings``: ``{name: {"options": [...], "active": value}}``.

        ``options`` lists the values a setting may take, or describes them
        when they cannot be listed. ``active`` is the value used when the
        setting is left out of ``acquire``.
        """
        raise NotImplementedError("ZmartDriver.get_acquisition_settings: return True, settings")

    def acquire(self, position_label, acquisition_settings):
        """Capture here, save, and return ``True, (files, planes)``, or ``False, message``.

        Name the saved files after ``position_label`` and never overwrite an
        earlier one. ``files`` lists the path of every file saved. ``planes``
        has one entry per saved image plane: its ``path``, its ``c``, ``z``
        and ``t`` counted from 0, and ``x_um``, ``y_um``, ``z_um``, the
        stage position it was taken at. Raise ``ValueError`` for an
        acquisition setting that is not listed. When no complete file ever
        appears, return ``False`` and say so.
        """
        raise NotImplementedError(
            "ZmartDriver.acquire: capture, save, then return True, (files, planes)"
        )

    def get_procedures(self):
        """Return ``True, procedures``: ``{name: {"description": ...}}``, the routines offered."""
        raise NotImplementedError("ZmartDriver.get_procedures: return True, procedures")

    def run_procedure(self, procedure):
        """Run the routine named by ``procedure["name"]`` and return ``True, name``, or ``False, message``.

        The other keys of ``procedure`` are its arguments. Raise
        ``ValueError`` for a name that ``get_procedures`` does not list.
        """
        raise NotImplementedError("ZmartDriver.run_procedure: run it, then return True, name")
