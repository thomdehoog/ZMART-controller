"""The code that talks to your microscope's vendor software. Fill in every method.

The controller creates one ``ZmartDriver`` when it connects, and hands it
back to every command as the handle. Its plugin then calls the method of
the same name here and wraps what it hands back in the answer shape the
controller expects.
So each method returns plain values, exactly the ones named in the plugin,
and never the ``{"success", "content"}`` wrapping.

A class is a bundle of data and the functions that work on it. Here the
data is whatever you need to keep while connected, such as the vendor's
connection object, and ``self`` is how each method reaches it.

Positions are micrometres from the origin, the saved zero point of this
microscope. In a saved image, right is +x and down is +y. Raise
``ValueError`` for a request that is wrong, such as a position outside the
travel or an unknown setting, and ``RuntimeError`` when the microscope
fails. The controller answers ``success: False`` with the error text.
Every method below raises ``NotImplementedError`` until you write it, so
``validate_driver`` tells you what is still missing.
"""


class ZmartDriver:
    """One connected microscope: the vendor connection and everything to drive it."""

    def __init__(self, connection):
        """Open the connection to the vendor software and keep what you need on ``self``.

        ``connection`` is the dictionary from ``zmart_driver.json``, or
        the one given at ``set_instrument``: which microscope, how its software
        is reached, where it listens, its password, and its configuration file.
        Where images are saved is your choice here; ``get_info`` reports it.
        """
        raise NotImplementedError("ZmartDriver.__init__: open the connection")

    def disconnect(self):
        """Close the connection to the vendor software."""
        raise NotImplementedError("ZmartDriver.disconnect: close the connection")

    def get_info(self):
        """Return ``output_root``, the folder where images are saved, and ``description``.

        The description is the microscope in plain words: what each changeable
        setting means, its unit and bounds, which objective sits in which slot,
        and which way +z points.
        """
        raise NotImplementedError("ZmartDriver.get_info: return output_root, description")

    def get_actuators(self):
        """Return the motor names that can move x, y and z: three lists, at least one name each."""
        raise NotImplementedError("ZmartDriver.get_actuators: return x_motors, y_motors, z_motors")

    def get_xyz(self, with_actuators):
        """Read the stage: return x, y, z in micrometres from the origin, and the motor read per axis.

        ``with_actuators`` names the motor to read per axis, such as
        ``{"z": "piezo"}``, or is None. An axis left out uses the first motor
        from ``get_actuators``. Raise ``ValueError`` for a motor name that is
        not listed.
        """
        raise NotImplementedError("ZmartDriver.get_xyz: return x, y, z, x_motor, y_motor, z_motor")

    def get_canvas(self):
        """Return everywhere a picture can show, per axis: x_min, x_max, y_min, y_max, z_min, z_max.

        That is the travel of each axis, widened by half a field of view, in
        micrometres from the origin. A viewer lays out the specimen area from it.
        """
        raise NotImplementedError(
            "ZmartDriver.get_canvas: return x_min, x_max, y_min, y_max, z_min, z_max"
        )

    def set_xyz(self, x, y, z, with_actuators):
        """Move the stage to x, y, z and return the motor used per axis.

        Check the travel limits first and raise ``ValueError`` for a position
        outside them. Read the position back until the stage has arrived, and
        raise ``RuntimeError`` when it cannot be confirmed: carrying on at an
        unknown position is never safe.
        """
        raise NotImplementedError(
            "ZmartDriver.set_xyz: move, then return x_motor, y_motor, z_motor"
        )

    def get_state(self):
        """Return two dictionaries: the ``changeable`` settings, and what is only ``observed``.

        Changeable settings, such as exposure time, are what ``set_state``
        applies. Observed values, such as the objective in place, describe the
        microscope and are never used as instructions.
        """
        raise NotImplementedError("ZmartDriver.get_state: return changeable, observed")

    def set_state(self, changeable):
        """Apply each setting in ``changeable`` and return a dictionary of what was applied.

        Raise ``ValueError`` for a setting name the microscope does not have.
        Read each setting back to confirm it took, and raise
        ``RuntimeError`` saying which one did not.
        """
        raise NotImplementedError("ZmartDriver.set_state: apply the settings and return applied")

    def get_acquisition_settings(self):
        """Return the choices for one acquisition: ``{name: {"options": [...], "active": value}}``.

        ``options`` lists the values a setting may take, or describes them when
        they cannot be listed. ``active`` is the value used when the setting is
        left out of ``acquire``.
        """
        raise NotImplementedError("ZmartDriver.get_acquisition_settings: return the settings")

    def acquire(self, position_label, acquisition_settings):
        """Capture an image here, save it, and return ``files`` and ``planes``.

        Name the saved files after ``position_label`` and never overwrite an
        earlier one. ``files`` lists the path of every file saved. ``planes``
        has one entry per saved image plane: its ``path``, its ``c``, ``z`` and
        ``t`` counted from 0, and ``x_um``, ``y_um``, ``z_um``, the stage
        position it was taken at. Raise ``ValueError`` for an acquisition
        setting that is not listed, and ``RuntimeError`` when the capture
        was sent but no complete file ever appeared.
        """
        raise NotImplementedError("ZmartDriver.acquire: capture, save, then return files, planes")

    def get_procedures(self):
        """Return the routines this microscope offers: ``{name: {"description": ...}}``."""
        raise NotImplementedError("ZmartDriver.get_procedures: return the procedures")

    def run_procedure(self, procedure):
        """Run the routine named by ``procedure["name"]``; the other keys are its arguments.

        Raise ``ValueError`` for a name that ``get_procedures`` does not list.
        """
        raise NotImplementedError("ZmartDriver.run_procedure: run the procedure")
