# 1. Plug in a driver

How the ZMART Controller connects to a microscope, and what a driver must
provide to make that work.

This page is the reference. For a step-by-step walk-through that builds a
small driver and plugs it in, open the [tutorial notebook](tutorial.ipynb).

## Contents

1. [What a driver is](#what-a-driver-is)
2. [Install a driver into the controller](#install-a-driver-into-the-controller)
3. [Writing the zmart_controller_plugin](#writing-the-zmart_controller_plugin)
4. [The functions](#the-functions)
5. [Positions and the canvas](#positions-and-the-canvas)
6. [What an acquisition reports](#what-an-acquisition-reports)
7. [State, acquisition settings and description](#state-acquisition-settings-and-description)
8. [Rules for every driver](#rules-for-every-driver)
9. [The configuration folder](#the-configuration-folder)
10. [Check a driver](#check-a-driver)

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


## Writing the zmart_controller_plugin

The functions the controller calls live together in one file, called
`zmart_controller_plugin.py`. A driver may consist of many files, such as
the mock driver with its folders for talking to the vendor software, handling
errors and saving data, but this one file is its front door. It is the only
file the controller needs to know about.

```python
# zmart_controller_plugin.py

NAME = "my-scope"                     # the driver's name in the controller's list

CONNECTION = {                        # how to reach this microscope; get_instruments() shows it
    "microscope": "my-scope-01",      # which instrument this is
    "api_type": "socket",             # how the vendor software is reached
    "host": "127.0.0.1",              # where it listens
    "password": "",                   # never shown by get_instruments()
    "config": "C:/my-scope/config.ini",
    "output_root": "D:/images",       # where images are saved
}


def connect(connection):
    return handle                     # any object that holds the live connection


def disconnect(handle):               # optional
    return None


def get_info(handle):
    return {"success": True, "content": {"output_root": "D:/images", "description": "..."}}


def get_actuators(handle):
    return {"success": True, "content": {"x": ["motor"], "y": ["motor"], "z": ["motor", "piezo"]}}


def get_xyz(handle, *, with_actuators=None):
    return {"success": True, "content": {
        "x": {"value": 0.0, "actuator": "motor", "canvas": [-5000.0, 5000.0]},
        "y": {"value": 0.0, "actuator": "motor", "canvas": [-5000.0, 5000.0]},
        "z": {"value": 0.0, "actuator": "motor", "canvas": [-500.0, 500.0]},
    }}


def set_xyz(handle, x, y, z, *, with_actuators=None):
    return {"success": True, "content": {
        "position": {"x": x, "y": y, "z": z},
        "actuators": {"x": "motor", "y": "motor", "z": "motor"},
    }}


def get_state(handle):
    return {"success": True, "content": {"changeable": {"exposure_ms": 10.0}, "observed": {"objective": "10x"}}}


def set_state(handle, state):
    return {"success": True, "content": {"applied": {"exposure_ms": 10.0}}}


def get_acquisition_settings(handle):
    return {"success": True, "content": {"format": {"options": ["ome-tiff", "ome-zarr"], "active": "ome-tiff"}}}


def acquire(handle, *, position_label, acquisition_settings=None):
    return {"success": True, "content": {
        "position_label": position_label,
        "files": ["D:/images/A1.ome.tif"],
        "planes": [{"path": "D:/images/A1.ome.tif", "c": 0, "z": 0, "t": 0,
                    "x_um": 0.0, "y_um": 0.0, "z_um": 0.0}],
    }}


def get_procedures(handle):
    return {"success": True, "content": {"autofocus": {"description": "..."}}}


def run_procedure(handle, procedure):
    return {"success": True, "content": {"ran": procedure["name"]}}
```

Each `return` above shows the least every answer must contain; the values
are examples. The sections below say what each key means. A driver may add
keys of its own to any answer.

`NAME` is the name the driver is listed under once it is installed.
`CONNECTION` is how to reach this microscope. The controller hands it to
`connect` unchanged and reads nothing from it itself, so a driver may use
other keys, but every driver should start from the five above: which
instrument this is, how its vendor software is reached, where it listens,
the password, and the vendor's configuration file. Leave a key empty when
the microscope does not need it. `get_instruments()` shows the connection
of every installed driver, with password, token and secret keys left out,
so anyone at the computer can see how each microscope is reached. Both are
only read for an installed driver. While you write a driver and hand the
module to `set_instrument` yourself, neither is needed.

While a driver is small it can be this single file. Once it grows, make it
a package: a folder with an `__init__.py` that imports the functions from
`zmart_controller_plugin.py`, exactly as the mock does. The controller finds
the functions by name on whatever it is given, so the file can also import
them from elsewhere.

## The functions

`connect` receives the connection dictionary and returns a **handle**. The
handle is any object that holds the live connection to the microscope. It
can be a plain dictionary, or an object from the vendor's own library. Every
other function receives that handle as its first argument. The controller
never looks inside it; it only hands it back to your functions.

```
connect(connection) ──► handle ──► get_xyz(handle, ...)
                                   set_xyz(handle, x, y, z, ...)
                                   acquire(handle, ...)
```

Every function except `connect` and `disconnect` answers in the same shape:

```python
{"success": True, "content": {...}}
```

`success` says whether the driver did what was asked. `content` is what the
driver has to say about it. The table lists what `content` must contain, so
that a workflow written for one microscope keeps working on another. A driver
may add keys of its own to any answer. It must not leave the required ones
out.

| Function | Receives | `content` must contain |
|---|---|---|
| `connect` | the connection dictionary | *(returns a handle instead)* |
| `disconnect` *(optional)* | handle | *(returns nothing; afterwards every other call should raise `RuntimeError`)* |
| `get_info` | handle | `output_root`: the folder where images are saved. Recommended: `description`, see [below](#state-acquisition-settings-and-description) |
| `get_actuators` | handle | `{axis: [motor names]}` for `x`, `y` and `z`, at least one motor each |
| `get_xyz` | handle, `with_actuators=` | `{axis: {"value", "actuator", "canvas"}}` for `x`, `y` and `z`, see [below](#positions-and-the-canvas) |
| `set_xyz` | handle, `x`, `y`, `z`, `with_actuators=` | `position`, the position asked for, and `actuators`, the motor used per axis. Raise if the move cannot be confirmed |
| `get_state` | handle | `changeable` and `observed`, see [below](#state-acquisition-settings-and-description) |
| `set_state` | handle, state | `applied`: the settings that were changed. Act on `changeable` only |
| `get_acquisition_settings` | handle | `{name: {"options": [...], "active": value}}` |
| `acquire` | handle, `position_label=`, `acquisition_settings=` | `position_label`, `files` and `planes`, see [below](#what-an-acquisition-reports) |
| `get_procedures` | handle | `{name: {"description": ...}}` |
| `run_procedure` | handle, `{"name": ..., ...}` | `ran`: the name of the procedure. Raise `ValueError` for an unknown name |

`with_actuators` is a dictionary that names the motor to use per axis, such
as `{"z": "piezo"}`. The names are the ones `get_actuators` listed. An axis
that is left out uses the first motor in its list. A name that is not in the
list should raise `ValueError`.

These names are the whole connection between the controller and a
microscope. The list of required ones is kept in
`zmart_controller.utils.OPS`. A helper function of your own in the driver
file must not reuse one of these names.

## Positions and the canvas

Positions are in **micrometres from the origin**. The origin is a point
(0, 0, 0) that was chosen and saved once for this microscope, so that a
position means the same place on the sample every time someone connects.
Turning the vendor's own numbers into this frame is the driver's job.

Positions and pictures share one frame. **In a saved image, right is +x and
down is +y**, on every microscope. If the vendor's images come out mirrored
or turned, the driver corrects them on saving. Which way +z points is the
microscope's own; say so in the `description`.

`get_xyz` reports, for each axis:

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

## What an acquisition reports

`acquire` captures an image at the current position with the current
settings, and saves it. Its `content` holds three things.

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

## State, acquisition settings and description

**The state** is the instrument's settings, captured by `get_state` so they
can be applied again later with `set_state`. It has two parts:

- `changeable`: the settings `set_state` applies, such as laser power or
  exposure time.
- `observed`: a read-only description, such as the objective in place and
  the pixel size. It is never used as an instruction.

Both are dictionaries. `set_state` receives a dictionary of the same shape,
applies what is under `changeable`, and reports what it changed under
`applied`.

**Acquisition settings** are the choices for one acquisition, such as the
file format or the number of planes in a z-stack. `get_acquisition_settings`
lists each one with:

- `options`: the values it may take. When they cannot be listed, a short
  description such as `"number > 0"`.
- `active`: the value used when the setting is left out of `acquire`.

**The description** in `get_info` is the microscope in plain words. It is
read by whoever drives the microscope: a person, a notebook, or the ZMART AI
agent. Say what the other answers cannot: what each setting in `changeable`
means, its unit and its bounds, which objective sits in which slot, which
way +z points, and anything about the sample worth knowing. Leave out what
`get_xyz` and `get_procedures` already report. A driver without a
description still works. When there is one, it must be text with something
in it.

Anything else in `get_info` is an extra of your driver. A workflow that
depends on it will not run on other microscopes.

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
a connection dictionary if the driver needs one. It connects, calls every `get_*` function, checks each answer against the
table above, and disconnects again. It moves nothing and acquires nothing.
It returns the problems it found, one plain sentence each, naming the
function and what is missing. An empty list means every answer fits.

Because it never takes a picture, one acquisition is checked separately:

```python
answer = zmart_controller.acquire(position_label="A2")
zmart_controller.check_acquire_answer(answer)
```

`check_acquire_answer` checks that `files` and `planes` are as described
[above](#what-an-acquisition-reports), including that every listed file
exists. A driver's own tests call it after an acquisition, on a simulator or
a test bench.

The loop to work in while you write a driver is this: change a function,
validate, read the problems, repeat.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
