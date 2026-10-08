# 1. Plug in a driver

How the ZMART Controller connects to a microscope, and what a driver must
provide to make that work.

This page is the reference. For a step-by-step walk-through that builds a
small driver and plugs it in, open the [tutorial notebook](tutorial.ipynb).

## Contents

1. [What a driver is](#what-a-driver-is)
2. [Install a driver into the controller](#install-a-driver-into-the-controller)
3. [The two files of a driver](#the-two-files-of-a-driver)
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

In short: a driver is two files, a small JSON with its name and how to
reach the microscope, and a `ZmartDriver` class with one method per
command. The controller does the plugging in.

## Install a driver into the controller

Installing a driver into the controller means telling it, once, where the
driver is on this computer, by pointing it at the driver's
`zmart_driver.json`:

```python
import zmart_controller

zmart_controller.register_driver("C:/drivers/my-scope/zmart_driver.json")
```

`register_driver` loads the driver and checks that its name and its
`ZmartDriver` class are there before it writes anything down. A driver
that cannot be imported, or that misses something, is refused with a
message that says what is wrong:

```
ValueError: driver my_driver is missing functions: ['set_xyz']
```

From then on the driver is on the list, and can be connected to by name:

```python
zmart_controller.get_instruments()           # {'mock': {}, 'my-scope': {'microscope': ..., 'host': ..., ...}}
zmart_controller.set_instrument("my-scope")
```

`get_instruments` lists every installed driver with how it connects,
without its password.

The mock driver is always on the list, and the name `"mock"` is taken.
The drivers for the microscopes at the ZMB are in
[ZMART drivers](https://github.com/thomdehoog/ZMART-drivers).

## The two files of a driver

A driver is a folder with two files, and both are yours:

- `zmart_driver.json` holds the driver's name, where its class file is,
  and how to reach the microscope. It is what you point at to install the
  driver.
- `zmart_driver.py` holds the `ZmartDriver` class, which integrates the
  code that drives the microscope, one method per command. What each
  method hands back must comply with what the controller needs.

The controller ships both, ready to copy, in the folder
`zmart_controller/template`. Copy that folder, rename it, and adapt the
two files.

### The settings: zmart_driver.json

The driver's name and the connection are not in the code. They are in
`zmart_driver.json`, so that whoever sets up the microscope computer can
edit them without touching Python. Each value below says what to put
there; the shipped file looks the same, and you replace every value:

```json
{
  "name": "<the name you want the driver listed under by get_instruments(), for example stellaris>",
  "driver": "<the file that holds your ZmartDriver class; leave it unless you moved the file>",
  "connection": {
    "microscope": "<a name for this particular instrument, for example stellaris5-room-42>",
    "api_type": "<how the vendor software is reached, for example socket, grpc or dll>",
    "host": "<if the vendor software listens on a network address, put it here>",
    "password": "<if the vendor software requires a password or token, put it here>",
    "config": "<if the vendor software has a configuration file, put its path here>"
  }
}
```

`get_instruments()` shows this back for every installed driver.

### The ZmartController

One class, `ZmartController`, in `zmart_controller/zmart_controller.py`.

**In:** your `ZmartDriver`. Making a controller makes one from the
connection, and every command becomes a call to the method of the same
name on it.

```python
from zmart_controller import ZmartController
from zmart_driver import ZmartDriver

mic = ZmartController(ZmartDriver, connection)   # while writing the driver
mic = ZmartController("my-scope")                # once installed: the JSON gives both
mic.set_xyz(100, 50, 0)
```

**Out:** one answer shape for every command, built from what your method
hands back.

| Your method | The answer |
|---|---|
| returns | `{"success": True, "content": {...}}`, your values under fixed keys |
| raises `NotConfirmed("...")` | `{"success": False, "content": "..."}`, your text |
| raises `ValueError` or `RuntimeError` | the error itself, unchanged |

So what is left for you is to write a `ZmartDriver` class that complies
with the following.

## Writing the ZmartDriver

`ZmartDriver` in `zmart_driver.py` is where you write the code that drives
the vendor software. A class is a bundle of data and the functions that
work on it, called methods. Making a `ZmartDriver` opens the vendor
connection and keeps it on `self`, and each method does one command with
it. Every method starts out raising `NotImplementedError`, with a docstring
saying what it must hand back, so `validate_driver` tells you which one is
still to write.

The controller calls these methods and expects their answers in a fixed form.
Each method returns the plain values named beside it, never the `success`
and `content` wrapping; the controller adds that. The headings below show the method, what it returns,
and what the controller then puts in `content`.

### Connect and disconnect

```python
def __init__(self, connection): ...    # open the vendor connection, keep what you need on self
def disconnect(self): ...              # close it; afterwards every other call should raise RuntimeError
```

On the controller's side, making the `ZmartDriver` is the connection, and
the object is kept as the handle that every command receives:

```python
# zmart_controller/zmart_controller.py

self._handle = driver_class(connection)
```

```python
# zmart_controller/zmart_controller.py

def disconnect(handle):

    handle.disconnect()

    return None
```

`connection` is the one from `zmart_driver.json`, or the dictionary given
at `set_instrument`. Load what was saved once for this microscope here too:
the origin, the travel limits and the calibration, from the
[configuration folder](#the-configuration-folder).

### Describe the microscope: get_info

```python
def get_info(self): ...                # returns output_root, description
```

On the controller's side, this is what receives it:

```python
# zmart_controller/zmart_controller.py

def get_info(handle):

    output_root, description = handle.get_info()

    return {"success": True, "content": {"output_root": output_root, "description": description}}
```

`output_root` is the folder where images are saved. `description` is the
microscope in plain words, read by whoever drives it: a person, a notebook,
or the ZMART AI agent. Say what the other answers cannot: what each
changeable setting means, its unit and its bounds, which objective sits in
which slot, which way +z points, and anything about the sample worth
knowing. Leave out what `get_xyz` and `get_procedures` already report. It
must be text with something in it.

The controller puts both in `content`. Anything else a driver adds there is an
extra of that driver, and a workflow that depends on it will not run on
other microscopes.

### Position: get_actuators, get_xyz, get_canvas, set_xyz

```python
def get_actuators(self): ...                      # returns x_motors, y_motors, z_motors
def get_xyz(self, with_actuators): ...            # returns x, y, z, x_motor, y_motor, z_motor
def get_canvas(self): ...                         # returns x_min, x_max, y_min, y_max, z_min, z_max
def set_xyz(self, x, y, z, with_actuators): ...   # moves, then returns x_motor, y_motor, z_motor
```

On the controller's side, this is what receives it:

```python
# zmart_controller/zmart_controller.py

def get_actuators(handle):

    x_motors, y_motors, z_motors = handle.get_actuators()

    return {"success": True, "content": {"x": x_motors, "y": y_motors, "z": z_motors}}


def get_xyz(handle, *, with_actuators=None):

    x, y, z, x_motor, y_motor, z_motor = handle.get_xyz(with_actuators)
    x_min, x_max, y_min, y_max, z_min, z_max = handle.get_canvas()

    return {
        "success": True,
        "content": {
            "x": {"value": x, "actuator": x_motor, "canvas": [x_min, x_max]},
            "y": {"value": y, "actuator": y_motor, "canvas": [y_min, y_max]},
            "z": {"value": z, "actuator": z_motor, "canvas": [z_min, z_max]},
        },
    }


def set_xyz(handle, x, y, z, *, with_actuators=None):

    x_motor, y_motor, z_motor = handle.set_xyz(x, y, z, with_actuators)

    return {
        "success": True,
        "content": {
            "position": {"x": x, "y": y, "z": z},
            "actuators": {"x": x_motor, "y": y_motor, "z": z_motor},
        },
    }
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

For `get_xyz`, the controller builds `content` per axis from the position and
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
controller reports `position`, the position asked for, and `actuators`, the
motor used per axis.

### Settings: get_state, set_state

```python
def get_state(self): ...               # returns changeable, observed
def set_state(self, changeable): ...   # applies them, returns applied
```

On the controller's side, this is what receives it:

```python
# zmart_controller/zmart_controller.py

def get_state(handle):

    changeable, observed = handle.get_state()

    return {"success": True, "content": {"changeable": changeable, "observed": observed}}


def set_state(handle, state):

    applied = handle.set_state(state["changeable"])

    return {"success": True, "content": {"applied": applied}}
```

The state is the instrument's settings, captured by `get_state` so they can
be applied again later with `set_state`. It has two dictionaries:

- `changeable`: the settings `set_state` applies, such as laser power or
  exposure time.
- `observed`: a read-only description, such as the objective in place and
  the pixel size. It is never used as an instruction.

The controller hands `set_state` only the `changeable` part of what the
workflow sent. Apply each setting, read it back to confirm it took, raise
`ValueError` for a name the microscope does not have, and return what was
applied; the controller reports it under `applied`.

### Acquire: get_acquisition_settings, acquire

```python
def get_acquisition_settings(self): ...                      # returns {name: {"options": [...], "active": value}}
def acquire(self, position_label, acquisition_settings): ... # captures and saves, returns files, planes
```

On the controller's side, this is what receives it:

```python
# zmart_controller/zmart_controller.py

def get_acquisition_settings(handle):

    settings = handle.get_acquisition_settings()  # {name: {"options": [...], "active": value}}

    return {"success": True, "content": settings}


def acquire(handle, *, position_label, acquisition_settings=None):

    files, planes = handle.acquire(position_label, acquisition_settings)

    return {
        "success": True,
        "content": {
            "position_label": position_label,
            "files": files,  # the path of every file saved
            "planes": planes,  # [{"path", "c", "z", "t", "x_um", "y_um", "z_um"}, ...]
        },
    }
```

Acquisition settings are the choices for one acquisition, such as the file
format or the number of planes in a z-stack. For each one, `options` lists
the values it may take, or describes them when they cannot be listed, such
as `"number > 0"`, and `active` is the value used when the setting is left
out of `acquire`. An acquisition setting that is not listed raises
`ValueError`.

`acquire` captures an image at the current position with the current
settings, and saves it. The controller puts three things in `content`:

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

On the controller's side, this is what receives it:

```python
# zmart_controller/zmart_controller.py

def get_procedures(handle):

    procedures = handle.get_procedures()  # {name: {"description": ...}}

    return {"success": True, "content": procedures}


def run_procedure(handle, procedure):

    handle.run_procedure(procedure)

    return {"success": True, "content": {"ran": procedure["name"]}}
```

Procedures are the routines a microscope offers, such as autofocus or
parking the stage. `procedure` is a dictionary whose `name` picks one; its
other keys are the arguments. A name that `get_procedures` does not list
raises `ValueError`. The controller reports `ran`, the name of the procedure.

## Rules for every driver

- **Raise when carrying on is unsafe.** Raise `ValueError` when the request
  is wrong: an unknown setting, a position outside the limits. Raise
  `RuntimeError` when the microscope fails. The controller passes the error
  on to the workflow unchanged, so the message should say what happened in
  plain words.
- **Report soft failures by raising `NotConfirmed`.** Use it only for an
  outcome a workflow can safely carry on from. The answer is
  `success: False`, and `content` is your error text.
- **Read back to confirm.** Microscope software often accepts a command
  before it has happened. When a setting or an acquisition was sent but never
  showed up, raise `NotConfirmed` saying so. A move is the exception:
  `set_xyz` raises `RuntimeError`, because carrying on at an unknown
  position is never safe.
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
this, the **configuration folder**, and `zmart_controller.registry.config_root()`
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
my_driver = zmart_controller.load_driver("C:/drivers/my-scope/zmart_driver.json")
zmart_controller.validate_driver(my_driver)
```

`load_driver` reads a driver's folder without installing it, which is how
you work while writing one; `set_instrument` takes what it returns too.
`validate_driver` takes a driver, as an installed name or as loaded here,
and a connection dictionary when the one in the JSON is not the one to use. It connects, calls every `get_*` function, checks each answer against
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
