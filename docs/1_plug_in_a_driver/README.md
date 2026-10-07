# 1. Plug in a driver

Connect the ZMART Controller to a microscope.

This is part 1 of two; see the [overview](../../README.md). It explains
what a driver is, where its functions go, what each function must do, and how
to check that a driver fits. The [tutorial](tutorial.md) is a step-by-step
walk-through: it plugs in the mock driver and then builds a small driver of
your own. This page is the complete documentation of part 1.

## Contents

1. [The idea](#the-idea)
2. [Plug in a driver](#plug-in-a-driver)
3. [Where the functions go](#where-the-functions-go)
4. [The requirements](#the-requirements)
5. [Positions, travel and canvas](#positions-travel-and-canvas)
6. [What an acquisition reports](#what-an-acquisition-reports)
7. [State, settings and description](#state-settings-and-description)
8. [Rules every driver follows](#rules-every-driver-follows)
9. [Configuration: what a driver measures once](#configuration-what-a-driver-measures-once)
10. [Check that a driver fits](#check-that-a-driver-fits)
11. [How a driver is built inside](#how-a-driver-is-built-inside)
12. [Install a driver](#install-a-driver)

## The idea

Your workflow speaks to the controller in a short list of commands: move,
read and apply the state, acquire, run a procedure. The controller does not
know any microscope. It hands every command to a **driver**, and the driver
carries it out on its own microscope.

A driver is nothing more than **one Python function per command**, collected
in a module. There is no class to inherit from and no file to register. You
hand the module to the controller, and from then on every command goes to it:

```
  your workflow ──► zmart_controller ──► driver ──► vendor software ──► microscope
                     set_xyz(...)         set_xyz(handle, ...)
```

Because every driver has the same functions and answers in the same shape,
the same workflow runs on any microscope that has one. The controller ships
with one complete driver, the **mock driver** (`zmart_controller.mock`): a
simulated microscope that runs on any computer, so you can try everything at
your desk.

## Plug in a driver

```python
import zmart_controller

zmart_controller.set_instrument(zmart_controller.mock)
```

`set_instrument` takes the driver and, if the driver needs it, a
**connection dictionary**: whatever that microscope needs to connect, such as
a host name or a folder for the images. The controller hands it to the
driver's `connect` unchanged.

```python
zmart_controller.set_instrument(zmart_controller.mock, {"output_root": "D:/images"})
```

Before connecting, the controller checks that the driver has every required
function, and refuses one that is missing by name:

```
ValueError: driver my_driver is missing functions: ['set_xyz']
```

From then on, `zmart_controller.set_xyz(...)`, `zmart_controller.acquire(...)`
and every other command go to that microscope, until you call
`zmart_controller.disconnect()` or plug in another driver. Plugging in a new
driver disconnects the previous one.

**Several microscopes at once.** Hold a session for each instead of using the
module directly:

```python
from zmart_controller.session import set_instrument

left = set_instrument(zmart_controller.mock)
right = set_instrument(my_driver, {"host": "scope-2"})
left.acquire(position_label="A1")
right.acquire(position_label="A1")
```

A session has the same commands as the module. Each one talks only to its
own microscope.

## Where the functions go

**A small driver is a single Python file.** Put the functions in it and
import it:

```
pretend_scope.py        connect, get_info, get_xyz, set_xyz, acquire, ...
```

```python
import pretend_scope

zmart_controller.set_instrument(pretend_scope)
```

The controller finds the functions by their names, so the names must be
exactly those in the table below. Anything else in the file (helper
functions, constants) is ignored. A dictionary from command name to function
works too, which is handy in tests.

**A larger driver is a package**, a folder of Python files, whose
`__init__.py` makes the functions available by name. The mock driver is
built this way, and is the example to copy:

```
zmart_controller/mock/
    __init__.py          imports the functions from driver.py, which makes this folder a driver
    driver.py            the functions the controller calls, one per command
    vendor_interface/    talks to the vendor software
    error_handling/      sorts every problem into a kind, and says what to do
    get_actions/         asks the microscope things
    set_actions/         changes the microscope, then confirms the change
    procedures/          recipes such as autofocus
    data_handling/       turns the vendor's files into OME-TIFF or OME-Zarr
    configuration/       origin, limits, registration, calibration
    testing/mock_api/    the pretend vendor software the mock runs on
```

Its `__init__.py` holds little more than this:

```python
from .driver import (
    acquire,
    connect,
    disconnect,
    get_acquisition_settings,
    ...
)
```

so `zmart_controller.set_instrument(zmart_controller.mock)` finds every
function on the package itself. Your own driver works the same way:
`set_instrument(my_driver)`, where `my_driver` is the package.

## The requirements

`connect` receives the connection dictionary and returns a **handle**: any
object you like that holds the live connection to your microscope. Every
other function receives that handle as its first argument. The controller
never looks inside the handle.

```
  connect(connection) ──► handle ──► get_xyz(handle, ...)
                                     set_xyz(handle, x, y, z, ...)
                                     acquire(handle, ...)
                                     ...
```

Every function except `connect` and `disconnect` returns the same two things:

```python
{"success": True, "content": {...}}
```

`success` says whether the driver did what was asked. `content` is what it
has to say about it. The table gives what the `content` must contain, so
that a workflow written for one microscope keeps working on another. A driver
may add keys of its own; it should not leave out the ones listed here.

| Function | Receives | The `content` must contain |
|---|---|---|
| `connect` | the connection dictionary | *(returns a handle: anything)* |
| `disconnect` *(optional)* | handle | *(returns nothing; afterwards every other call raises `RuntimeError`, and a second `disconnect` is harmless)* |
| `get_info` | handle | `output_root`, the folder where images are saved; and, recommended, `description` |
| `get_actuators` | handle | `{axis: [motor names]}` for `x`, `y` and `z`, at least one motor each |
| `get_xyz` | handle, `with_actuators=` | `{axis: {"value", "actuator", "canvas"}}` for `x`, `y` and `z`; `value` and `canvas` in micrometres from the origin |
| `set_xyz` | handle, `x`, `y`, `z`, `with_actuators=` | `position` and `actuators`; raise if the move cannot be confirmed |
| `get_state` | handle | `{"changeable": {...}, "observed": {...}}` |
| `set_state` | handle, state | what was applied; act on `changeable` only |
| `get_acquisition_settings` | handle | `{name: {"options": [...], "active": value}}` |
| `acquire` | handle, `position_label=`, `acquisition_settings=` | `position_label`; `files`, the path of every file the acquisition saved; and `planes`, one entry per saved image plane |
| `get_procedures` | handle | `{name: {"description": ..., ...}}` |
| `run_procedure` | handle, `{"name": ..., ...}` | `ran`, the name of the procedure; raise `ValueError` for an unknown name |

`with_actuators` names the motor to use per axis, for example
`{"z": "piezo"}`, from the names `get_actuators` lists. Left out, the driver
uses its default motor.

## Positions, travel and canvas

Positions are in **micrometres from the origin**: a point on the microscope,
recorded once during setup, that reads as (0, 0, 0). How the origin is found
and stored is the driver's business (see [Configuration](#configuration-what-a-driver-measures-once)).

For each axis, `get_xyz` reports:

- `value`: where the axis is now.
- `canvas`: `[min, max]`, everywhere a picture can show on that axis.

The canvas is the stage's travel widened a little, because a picture taken at
the end of the travel still shows half a field of view beyond it, and a
z-stack started at the top or bottom of the focus shows half a stack further.
So the canvas is the travel widened by half the largest field the driver can
take (for x and y) and half the deepest stack (for z). When nothing can be
seen beyond the travel on some axis, the canvas is the travel itself there.
The interface and the viewer use it to lay out the whole specimen area before
the first picture arrives, so nothing has to grow or shift later.

The travel limits themselves stay inside the driver: a move outside them is
refused with a `ValueError` before anything moves.

**One frame for positions and pictures.** The positions and the pictures
share the frame in which you observe the specimen: in a saved image, **right
is +x and down is +y**. A picture taken further along +x shows the part of
the specimen that lay to its right. The driver arranges this, however the
camera or the stage is mounted, so that left, right, up and down mean the same
on every microscope, both to a person reading the images and to a workflow that
moves the stage from them. Which way +z points (towards the objective or away
from it) is the microscope's own; a driver says so in its `description`.

## What an acquisition reports

`acquire` captures an image at the current position with the current
settings, and saves it, in one step. Its content holds three things.

**`position_label`** is the name the workflow gave this position, such as
`"A1"`. The driver names the saved files after it and repeats it in the
content.

**`files`** lists everything the acquisition saved: the images, and any file
the driver saved beside them, such as a log. A format kept as a folder, such
as OME-Zarr, is listed by its folder. Every path must exist when `acquire`
returns. This is how a workflow finds its pictures on any microscope, so it
never has to guess a path. An acquisition that did not succeed may list none.

Where the files go, beyond being named after the label, is the driver's
choice. If a person should be able to choose, offer it as an acquisition
setting, the way the mock offers `folder`.

**`planes`** says where each saved picture sits on the sample. A file says how
large a pixel is, but rarely where the stage stood, and a stack is taken with
the stage at one place while its planes spread above and below it. Only the
driver knows, at the moment it acquires, so it says so here. Each entry
describes one **image plane**: a single picture of one channel at one depth
and one moment.

| Key | What it is |
|---|---|
| `path` | the file the plane is in; one of `files` |
| `c` | which channel, counted from 0 in the order the microscope records them |
| `z` | which depth of the stack, counted from 0 from the first plane taken; 0 for a single plane |
| `t` | which moment, counted from 0; 0 for an acquisition taken once |
| `x_um`, `y_um` | the stage position the plane was taken at, in micrometres, in the frame `get_xyz` and `set_xyz` use |
| `z_um` | the height of this plane, in micrometres, in the same frame |

When a file holds many planes, such as a stack saved as one file, every plane
names that file, and `c`, `z` and `t` say where inside it the plane is. No two
planes may share the same `c`, `z` and `t`. A position the driver genuinely
cannot know is `None` rather than a guess, because a picture laid down in the
wrong place is worse than one left unplaced. A driver may add entries of its
own to a plane, such as a channel's name; nothing relies on them, so a
workflow meant for any microscope must not need them.

## State, settings and description

**The state** is the instrument's settings, captured by `get_state` so they
can be applied again later with `set_state`. It has two parts.
`"changeable"` holds the settings `set_state` applies, such as laser power
or exposure time. `"observed"` is a read-only description, such as which
objective is in place and the pixel size; it is never used as an instruction.

**Acquisition settings** are the choices for one acquisition, such as the
file format or the number of planes in a z-stack. `get_acquisition_settings`
lists each one with the values it may take (`"options"`) and the value used
when it is left out (`"active"`). When the allowed values cannot be listed,
`"options"` may be a short description, such as `"number > 0"`.

**`description`** in `get_info` is the microscope in plain words, for whoever
drives it: a person, a notebook, or the ZMART AI agent, which learns the
instrument from it. Say what the other answers cannot: what each setting in
`changeable` means, its unit and its bounds, which objective sits in which
slot, and anything about the sample or the images worth knowing. Leave out
what `get_xyz` and `get_procedures` already report, since those stay current
and a description does not. A driver without a description still works; only
the AI agent then has less to go on. When it is there, it must be text with
something in it.

Anything else in `get_info` is an extra of your driver. A workflow that
depends on it will not run on other microscopes.

## Rules every driver follows

- **Refuse by raising; report soft outcomes.** When carrying on would be
  unsafe, raise: `ValueError` when the request itself is wrong (an unknown
  setting, a position outside the limits), `RuntimeError` when the
  microscope fails or refuses. The controller passes your error to the
  workflow unchanged. Use `success: False` only for an outcome it is safe to
  carry on from, and say what happened in the `content`.
- **Say when a change could not be confirmed.** Microscope software often
  accepts a command before it has happened, so read back to check. When a
  setting or an acquisition was sent but the readback never showed it,
  answer `success: False` with `"confirmed": False` and the reason in the
  `content`. A move is the exception: `set_xyz` raises `RuntimeError`,
  because carrying on at an unknown position is never safe.
- **Reject what you do not understand.** An unknown setting name or
  procedure raises `ValueError`. A typo that is silently ignored can cost
  someone an entire experiment.
- **Keep secrets out of error messages.** The connection dictionary may hold
  passwords. Name the keys, never the values.
- **Keep safety and configuration in the driver.** Travel limits, the origin
  and the calibration: only the driver knows the hardware. The controller
  checks nothing on the microscope's behalf.

## Configuration: what a driver measures once

Some things only the microscope itself can tell: where (0, 0, 0) is, how far
the stage may safely travel, which way the camera is mounted, how far each
objective's view is shifted. A driver measures them once, in a setup step of
its own, saves them, and loads them every time it connects.

They are saved on the microscope computer, never in a repository, so a fresh
download or an upgrade never loses them. Every ZMART driver uses the same
folder for this:

```python
from zmart_controller.utils import config_root

config_root()   # C:\ProgramData\zmart-microscopy on Windows
```

It is `C:\ProgramData\zmart-microscopy\` on Windows,
`/Library/Application Support/zmart-microscopy/` on macOS and
`/etc/zmart-microscopy/` on Linux. Set the environment variable
`ZMART_MICROSCOPY_ROOT` to use another folder, for example in tests. A driver
keeps its files in a folder of its own below it. The mock driver shows the
pattern in its `configuration/` part: a shipped `default.json` for each item,
used until something has been measured and saved.

## Check that a driver fits

Once a driver connects, let the controller check its answers:

```python
problems = zmart_controller.validate_driver(my_driver)
problems   # [] means it fits
```

`validate_driver` takes the same driver and connection dictionary as
`set_instrument`. It calls every `get_*` function and compares each answer
with the requirements above. The answer is a list of problems in plain
words, such as `"get_xyz: axis 'z' is missing 'canvas'"`. It moves nothing and
acquires nothing.

Because it acquires nothing, it cannot check `acquire`. Do that in your
driver's own tests, on a simulator or a test bench:

```python
answer = zmart_controller.acquire(position_label="A1")
assert zmart_controller.check_acquire_answer(answer) == []
```

`check_acquire_answer` checks `position_label`, that every file in `files`
exists, and every entry in `planes`.

The controller's own tests, in `tests/`, also show the behaviour a workflow
relies on. Running your driver through the same scenarios is a quick way to
find gaps.

## How a driver is built inside

A driver for a real microscope does more than map commands: it talks to
vendor software that is slow, busy, or sometimes wrong. The ZMART drivers
share one layout for this, so that the safety behaviour is the same on every
microscope and an unfamiliar driver is easy to find your way around. Each
part only uses the parts below it:

```
  driver.py             the functions the controller calls
  procedures            recipes such as autofocus, built from get and set actions
  set actions           change the microscope, then confirm the change
  get actions           ask the microscope something
  error handling        sort every problem into a kind, then follow the rule
  vendor interface      the only part that knows the vendor software
  ────────────────────────────────────────────────────────────────
  alongside: data handling, configuration, testing
```

[The anatomy of a ZMART driver](driver-anatomy.md) describes every part and
its rules. The mock driver is built exactly this way; its
[README](../../zmart_controller/mock/README.md) walks through the parts, and
shows how one move travels through them.

You do not need all of this to start. A driver that is a single file with the
functions above already works with every workflow; the
[tutorial](tutorial.md) builds one.

## Install a driver

A driver is an ordinary Python package. Install it into the same Python
environment as the controller, import it, and hand it to `set_instrument`:

```bash
pip install "git+https://github.com/<owner>/<my-driver>"
```

```python
import zmart_controller
import my_driver

zmart_controller.set_instrument(my_driver, {"host": "localhost"})
```

The drivers for the microscopes we use at the ZMB are in
[ZMART drivers](https://github.com/thomdehoog/ZMART-drivers). Each driver's
README says which module to import, what goes in its connection dictionary,
and how to run its setup step once on the microscope computer.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
