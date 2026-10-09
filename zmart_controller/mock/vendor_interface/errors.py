"""What can go wrong, in words every part of the driver shares.

The vendor interface promises that every failure it raises can be sorted
into one of a few shared kinds. This file keeps that promise. It holds the
error the vendor software raises (:class:`VendorError`), the list of kinds
(:class:`Kind`), and :func:`classify`, which sorts whatever went wrong into
a kind. The sorting is the one microscope-specific piece, because every
vendor reports problems in its own way: one as text, another as a numeric
status code. MockScope reports an error code, and that is what the sorting
reads. What to do about each kind is decided above, in the dispatcher's
rules, which never read an error message themselves.

One rule matters more than any other here: **an error we do not recognise
counts as permanent.** Trying again after an error we do not understand
could repeat something harmful, so the driver stops instead.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

from enum import Enum


class VendorError(Exception):
    """The vendor software refused a command and answered with an error code.

    ``code`` is the vendor's number (see the MockScope error table) and
    ``message`` its text. :func:`classify` below sorts these into kinds; nothing
    else in the driver looks at the code.
    """

    def __init__(self, command: str, code: int, message: str) -> None:
        super().__init__(f"{command} refused by the microscope software: {message} (code {code})")
        self.command = command
        self.code = code
        self.message = message


class Kind(Enum):
    """The kinds of problem a driver can meet.

    The first four are how the vendor software can fail, and :func:`classify`
    sorts every raised error into one of them. The last three are not errors
    the vendor raises but outcomes the dispatchers reach on their own: a
    request stopped by the limits gate, a reading that could not be trusted,
    and a change that was sent but never confirmed. They are listed here so
    that the rules for all of them stand in one table.
    """

    BAD_REQUEST = "bad request"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    CONNECTION_LOST = "connection lost"
    REFUSED_BY_LIMITS = "refused by limits"
    UNKNOWN_READING = "unknown reading"
    UNCONFIRMED = "unconfirmed"


# MockScope's error codes, sorted into kinds. Codes not listed here (such as
# 999, "Internal error") are unknown and therefore permanent.
_CODES: dict[int, Kind] = {
    100: Kind.TEMPORARY,  # system busy
    200: Kind.BAD_REQUEST,  # unknown command: a bug in this driver
    201: Kind.BAD_REQUEST,  # value out of range of the hardware's end stops
    202: Kind.BAD_REQUEST,  # unknown setting
    203: Kind.BAD_REQUEST,  # missing argument
    204: Kind.BAD_REQUEST,  # unknown argument
    205: Kind.BAD_REQUEST,  # invalid value
    206: Kind.BAD_REQUEST,  # folder does not exist
    300: Kind.PERMANENT,  # hardware fault
    401: Kind.PERMANENT,  # access denied
    402: Kind.CONNECTION_LOST,  # the session is gone
}


def classify(error: BaseException) -> Kind:
    """Return the kind of problem ``error`` represents."""
    if isinstance(error, VendorError):
        return _CODES.get(error.code, Kind.PERMANENT)
    if isinstance(error, TimeoutError):
        # The reply was lost. The command may or may not have happened, which
        # is why the set dispatcher reads back before deciding anything.
        return Kind.TEMPORARY
    if isinstance(error, ConnectionError):
        return Kind.CONNECTION_LOST
    return Kind.PERMANENT
