# 1. Plug in a driver

How the ZMART Controller connects to a microscope, and what a driver must
provide to make that work.

This page is the reference. For a step-by-step walk-through that builds a
small driver and plugs it in, open the [tutorial notebook](tutorial.ipynb).

## Contents

1. [What a driver is](#what-a-driver-is)
2. [Install a driver into the controller](#install-a-driver-into-the-controller)
3. [The zmart_controller_plugin](#the-zmart_controller_plugin)
4. [Writing the ZmartDriver](#writing-the-zmartdriver)
5. [Rules for every driver](#rules-for-every-driver)
6. [The configuration folder](#the-configuration-folder)
7. [Check a driver](#check-a-driver)

## What a driver is

Every microscope's software speaks its own language, so a workflow written
for one microscope does not run on another. The controller stands in
between. It knows nothing about any particular microscope. It takes a short,
fixed list of commands from your workflow and hands each one to a
**driver**. The driver is the set of files that knows how to talk to one microscope's
vendor software.

```
your workflow ──► zmart controller ──► driver ──► vendor software ──► microscope
```

In short: the driver is plugged in through one file, `zmart_controller_plugin.py`,
which the controller ships ready to copy. What you write is the `ZmartDriver`
class next to it, one method per command.

## Install a driver into the controller

Installing a driver into the controller means telling it, once, where the
driver's functions are on this computer, by pointing it at the driver's
`zmart_controller_plugin.py`:

```python
import zmart_controller

zmart_controller.register_driver("C:/drivers/my-scope/zmart_controller_plugin.py")
```

`register_driver` imports the file and checks that every function and the
`NAME` are there before it writes anything down. A file that cannot be
imported, or that misses something, is refused with a message that says
what is wrong:

```
ValueError: driver my_driver is missing functions: ['set_xyz']
```

From then on the driver is on the list, and can be connected to by name:

```python
zmart_controller.get_drivers()               # ['mock', 'my-scope']
zmart_controller.get_instruments()           # {'mock': {}, 'my-scope': {'microscope': ..., 'host': ..., ...}}
zmart_controller.set_instrument("my-scope")
```

`get_instruments` shows how each driver connects, without its password.

The mock driver is always on the list, and the name `"mock"` is taken.
The drivers for the microscopes at the ZMB are in
[ZMART drivers](https://github.com/thomdehoog/ZMART-drivers).

## The zmart_controller_plugin

The driver is plugged in through `zmart_controller_plugin.py`. It is the
only file the controller needs to know about, and you do not write it. The
controller ships it in the folder `zmart_controller/template`, together with
two files that are yours: `zmart_driver.json`, the driver's name and how to
reach the microscope, and `zmart_driver.py`, which holds the `ZmartDriver`
class to fill in. Copy the whole folder and rename it. This is how the
shipped plugin begins:

```python
# zmart_controller_plugin.py

import json
from pathlib import Path

from .zmart_driver import ZmartDriver  # zmart_driver.py: the code that talks to the vendor software

# The driver's name and how to reach this microscope live in zmart_driver.json,
# next to this file, so they can be edited without touching any code.
_SETTINGS = json.loads((Path(__file__).with_name("zmart_driver.json")).read_text())

NAME = _SETTINGS["name"]  # the driver's name in the controller's list
CONNECTION = _SETTINGS["connection"]  # how to reach this microscope; get_instruments() shows it


def connect(connection):

    handle = ZmartDriver(connection)

    return handle  # the connected driver; every other function receives it back
```

The name and the connection are not in the code. They are in
`zmart_driver.json`, next to the plugin, so that whoever sets up the
microscope computer can edit them without touching Python:

```json
{
  "name": "my-scope",
  "connection": {
    "microscope": "my-scope-01",
    "api_type": "socket",
    "host": "127.0.0.1",
    "password": "",
    "config": "C:/my-scope/config.ini",
    "output_root": "D:/images"
  }
}
```

`name` is the name the driver is listed under once it is installed.
`connection` is how to reach this microscope: which instrument this is,
how its vendor software is reached, where it listens, the password, the
vendor's configuration file, and where images are saved. The controller
hands it to `connect` unchanged and reads nothing from it itself, so a
driver may add keys, but every driver starts from these. Leave a key empty
when the microscope does not need it. `get_instruments()` shows the
connection of every installed driver, with password, token and secret keys
left out.

`connect` makes one `ZmartDriver` from the connection and returns it as the
**handle**. The controller never looks inside the handle; it hands it back
to every other function. Each of those calls the method of the same name
on the handle, and wraps what comes back in the shape every command shares:

```python
def get_info(handle):

    output_root, description = handle.get_info()

    return {"success": True, "content": {"output_root": output_root, "description": description}}
```

`success` says whether the driver did what was asked. `content` is what the
driver has to say about it. The next section goes through every method and
what the plugin puts in `content`. The function names in the plugin are the
whole connection between the controller and a microscope; the list is kept
in `zmart_controller.utils.OPS`. Do not rename them.

## Writing the ZmartDriver

`ZmartDriver` in `zmart_driver.py` is where you write the code that drives
the vendor software. A class is a bundle of data and the functions that
work on it, called methods. Making a `ZmartDriver` opens the vendor
connection and keeps it on `self`, and each method does one command with
it. Every method starts out raising `NotImplementedError`, with a docstring
saying what it must hand back, so `validate_driver` tells you which one is
still to write.

The plugin calls these methods and expects their answers in a fixed form.
To use it, you have to comply with the following. Each method returns the
plain values named beside it, never the `success` and `content` wrapping;
the plugin adds that. The headings below show the method, what it returns,
and what the plugin then puts in `content`.

### Connect and disconnect

```python
def __init__(self, connection): ...    # open the vendor connection, keep what you need on self
def disconnect(self): ...              # close it; afterwards every other call should raise RuntimeError
```

`connection` is `CONNECTION` from the plugin, or the dictionary given at
`set_instrument`. Load what was saved once for this microscope here too:
the origin, the travel limits and the calibration, from the
[configuration folder](#the-configuration-folder).

### Describe the microscope: get_info

```python
def get_info(self): ...                # returns output_root, description
```

`output_root` is the folder where images are saved. `description` is the
microscope in plain words, read by whoever drives it: a person, a notebook,
or the ZMART AI agent. Say what the other answers cannot: what each
changeable setting means, its unit and its bounds, which objective sits in
which slot, which way +z points, and anything about the sample worth
knowing. Leave out what `get_xyz` and `get_procedures` already report. It
must be text with something in it.

The plugin puts both in `content`. Anything else a driver adds there is an
extra of that driver, and a workflow that depends on it will not run on
other microscopes.

### Position: get_actuators, get_xyz, get_canvas, set_xyz

```python
def get_actuators(self): ...                      # returns x_motors, y_motors, z_motors
def get_xyz(self, with_actuators): ...            # returns x, y, z, x_motor, y_motor, z_motor
def get_canvas(self): ...                         # returns x_min, x_max, y_min, y_max, z_min, z_max
def set_xyz(self, x, y, z, with_actuators): ...   # moves, then returns x_motor, y_motor, z_motor
```

Positions are in **micrometres from the origin**. The origin is a point
(0, 0, 0) that was chosen and saved once for this microscope, so that a
position means the same place on the sample every time someone connects.
Turning the vendor's own numbers into this frame is the driver's job.

Positions and pictures share one frame. **In a saved image, right is +x and
down is +y**, on every microscope. If the vendor's images come out mirrored
or turned, the driver corrects them on saving. Which way +z points is the
microscope's own; say so in the `description`.

`get_actuators` lists the motors that can move each axis, at least one per
axis. `with_actuators` is a dictionary that names the motor to use per
axis, such as `{"z": "piezo"}`, or `None`. An axis left out uses the first
motor in its list. A name that is not in the list raises `ValueError`.

For `get_xyz`, the plugin builds `content` per axis from the position and
the canvas:

| Key | What it is |
|---|---|
| `value` | where the axis is now |
| `actuator` | the motor that was read |
| `canvas` | `[min, max]`: everywhere a picture can show on that axis |

The canvas is the stage's travel, widened by half a field of view. A picture
taken at the very edge of the travel still shows half a field beyond it. A
viewer uses the canvas to lay out the whole specimen area before the first
picture arrives, so it has to cover everything a picture could ever show.
Both ends are numbers in micrometres, and `min` is never larger than `max`.
The stage itself still stops at the travel limits.

`set_xyz` checks the travel limits first and raises `ValueError` for a
position outside them. It sends the move and reads the position back until
the stage has arrived, and raises `RuntimeError` when it cannot be
confirmed, because carrying on at an unknown position is never safe. The
plugin reports `position`, the position asked for, and `actuators`, the
motor used per axis.

### Settings: get_state, set_state

```python
def get_state(self): ...               # returns changeable, observed
def set_state(self, changeable): ...   # applies them, returns applied
```

The state is the instrument's settings, captured by `get_state` so they can
be applied again later with `set_state`. It has two dictionaries:

- `changeable`: the settings `set_state` applies, such as laser power or
  exposure time.
- `observed`: a read-only description, such as the objective in place and
  the pixel size. It is never used as an instruction.

The plugin hands `set_state` only the `changeable` part of what the
workflow sent. Apply each setting, read it back to confirm it took, raise
`ValueError` for a name the microscope does not have, and return what was
applied; the plugin reports it under `applied`.

### Acquire: get_acquisition_settings, acquire

```python
def get_acquisition_settings(self): ...                      # returns {name: {"options": [...], "active": value}}
def acquire(self, position_label, acquisition_settings): ... # captures and saves, returns files, planes
```

Acquisition settings are the choices for one acquisition, such as the file
format or the number of planes in a z-stack. For each one, `options` lists
the values it may take, or describes them when they cannot be listed, such
as `"number > 0"`, and `active` is the value used when the setting is left
out of `acquire`. An acquisition setting that is not listed raises
`ValueError`.

`acquire` captures an image at the current position with the current
settings, and saves it. The plugin puts three things in `content`:

| Key | What it is |
|---|---|
| `position_label` | the name the workflow gave this position, such as `"A1"`. The saved files are named after it |
| `files` | the path of every file the acquisition saved: the images, and anything saved beside them, such as a log |
| `planes` | one entry per saved image plane, saying which file it is in and where it sits on the sample |

`files` is how a workflow finds its pictures on any microscope. A driver that
keeps them under a name of its own, without listing them here, works with
none of the workflows. Every path listed must exist when `acquire` returns. A
format that is kept as a folder, such as OME-Zarr, is listed by its folder.
A successful acquisition lists at least one file. Never overwrite an earlier
picture: when the same label is used twice, save the second one under a
new name, as the mock does with `A1_001`.

Each entry of `planes` describes one image plane:

| Key | What it is |
|---|---|
| `path` | the file that holds the plane. It must be one of the `files` |
| `c`, `z`, `t` | the plane's channel, depth and time point, each counted from 0. They also find the plane inside a file that holds many |
| `x_um`, `y_um`, `z_um` | the stage position the plane was taken at, in micrometres from the origin. `None` where the driver cannot know it |

No two planes may share the same `c`, `z` and `t`. A driver may add entries
of its own to a plane. An acquisition that did not succeed may list no files
and no planes.

### Procedures: get_procedures, run_procedure

```python
def get_procedures(self): ...             # returns {name: {"description": ...}}
def run_procedure(self, procedure): ...   # runs the one named procedure["name"]
```

Procedures are the routines a microscope offers, such as autofocus or
parking the stage. `procedure` is a dictionary whose `name` picks one; its
other keys are the arguments. A name that `get_procedures` does not list
raises `ValueError`. The plugin reports `ran`, the name of the procedure.

## Rules for every driver

- **Raise when carrying on is unsafe.** Raise `ValueError` when the request
  is wrong: an unknown setting, a position outside the limits. Raise
  `RuntimeError` when the microscope fails. The controller passes the error
  on to the workflow unchanged, so the message should say what happened in
  plain words.
- **Report soft outcomes with `success: False`.** Use it only for an outcome
  a workflow can safely carry on from, and say what happened in `content`.
- **Read back to confirm.** Microscope software often accepts a command
  before it has happened. When a setting or an acquisition was sent but never
  showed up, answer `success: False` with `"confirmed": False` and the
  reason. A move is the exception: `set_xyz` raises `RuntimeError`, because
  carrying on at an unknown position is never safe.
- **Reject what you do not understand.** An unknown setting name,
  acquisition setting, motor name or procedure raises `ValueError`. A typo
  that passes silently can cost someone an experiment.
- **Keep secrets out of error messages.** The connection dictionary may hold
  passwords. Name the keys, never the values.
- **Keep safety in the driver.** Travel limits, the origin and the
  calibration belong to the driver. The controller checks nothing on the
  microscope's behalf.

## The configuration folder

What a driver measures once per microscope, such as the origin, the travel
limits and the calibration, belongs on the microscope computer, where every
user and every Python session finds it. The controller names one folder for
this, the **configuration folder**, and `zmart_controller.utils.config_root()`
returns it:

| System | Folder |
|---|---|
| Windows | `C:\ProgramData\zmart-microscopy` |
| macOS | `/Library/Application Support/zmart-microscopy` |
| Linux | `/etc/zmart-microscopy` |

Setting the environment variable `ZMART_MICROSCOPY_ROOT` points it somewhere
else, for example on a shared test computer. A driver's own setup step
writes its files under this folder, and its `connect` loads them. The
controller also keeps its list of installed drivers there, in `drivers.json`.
When this folder cannot be written, the list goes to `.zmart-microscopy` in
your home folder instead.

## Check a driver

The controller can check a driver's answers against the requirements on this
page, so you do not have to compare them by hand.

```python
zmart_controller.validate_driver(my_driver, {"host": "localhost"})
```

`validate_driver` takes a driver, as a registered name or as a module, and
a connection dictionary if the driver needs one. It connects, calls every `get_*` function, checks each answer against
this page, and disconnects again. It moves nothing and acquires nothing.
It returns the problems it found, one plain sentence each, naming the
function and what is missing. An empty list means every answer fits.

Because it never takes a picture, one acquisition is checked separately:

```python
answer = zmart_controller.acquire(position_label="A2")
zmart_controller.check_acquire_answer(answer)
```

`check_acquire_answer` checks that `files` and `planes` are as described
[above](#acquire-get_acquisition_settings-acquire), including that every listed file
exists. A driver's own tests call it after an acquisition, on a simulator or
a test bench.

The loop to work in while you write a driver is this: write a method,
validate, read the problems, repeat.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
