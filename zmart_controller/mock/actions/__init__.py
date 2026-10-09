"""Part 3 of the driver anatomy (``docs/driver-anatomy.md`` in ZMART-drivers): the actions.

Everything the driver asks the microscope to do, as short definitions that
the dispatcher runs. :mod:`.get` holds the readings: which primitive to call
and what the value means. :mod:`.set` holds the changes: which primitive to
call and how to confirm that the change took. A reading never changes the
microscope and never knows a target; a change confirms itself through the
readings, never the other way round.

Import the two by name, ``from ..actions import get`` and
``from ..actions import set as setter``, so that the built-in ``set`` is
never shadowed by accident.
"""
