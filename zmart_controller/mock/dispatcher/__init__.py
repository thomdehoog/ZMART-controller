"""Part 2 of the driver anatomy (``docs/driver-anatomy.md`` in ZMART-drivers): the dispatcher.

The engines that run an action safely, the same for every microscope.
:mod:`.read` runs a reading: one read at a time, a few tries after a
temporary problem, a time limit, and "unknown" rather than a guess.
:mod:`.change` runs a change: the limits gate first, then sending, retries,
reading back to confirm, sending again, and giving up softly when it cannot
confirm. :mod:`.gate` is the limits gate, :mod:`.rules` says what each engine
does for each kind of problem, and :mod:`.tuning` holds the retries and time
windows the driver author sets for this microscope.
"""

from .change import NeverConfirmed, Outcome, SetCommand, SetDispatcher
from .gate import Gate
from .read import GetDispatcher, Reading
from .rules import RULES, Action, Rule
from .tuning import (
    ACQUIRE_TUNING,
    DEFAULT_GET_TUNING,
    DEFAULT_SET_TUNING,
    OBJECTIVE_TUNING,
    GetTuning,
    SetTuning,
)

__all__ = [
    "ACQUIRE_TUNING",
    "DEFAULT_GET_TUNING",
    "DEFAULT_SET_TUNING",
    "OBJECTIVE_TUNING",
    "RULES",
    "Action",
    "Gate",
    "GetDispatcher",
    "GetTuning",
    "NeverConfirmed",
    "Outcome",
    "Reading",
    "Rule",
    "SetCommand",
    "SetDispatcher",
    "SetTuning",
]
