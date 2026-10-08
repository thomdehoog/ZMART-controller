# 1. Plug in a driver

Connect the ZMART Controller to a microscope.

This page is acts as documentation. For a step-by-step walk-through, open the
[tutorial notebook](tutorial.ipynb).

## Contents

1. [What a driver is](#what-a-driver-is)
2. [Plug one in](#plug-one-in)
3. [The driver file](#the-driver-file)
4. [The functions](#the-functions)
5. [Positions and the canvas](#positions-and-the-canvas)
6. [What an acquisition reports](#what-an-acquisition-reports)
7. [State, acquisition settings and description](#state-acquisition-settings-and-description)
8. [Rules for every driver](#rules-for-every-driver)
9. [The configuration folder](#the-configuration-folder)
10. [Check a driver](#check-a-driver)
11. [Register a driver](#register-a-driver)

## What a driver is

The controller is microscope-agnostic and acts as an messenger. It hands every command to a
**driver**. The driver is a set of files the communicates with the vendor software

```
your workflow ──► zmart controller ──► driver ──► vendor software ──► microscope
```

The controller ships with one driver, the **mock driver**. It is a simulated
microscope that runs on any computer, so you can try everything at your desk.

## Plug one in

```python
import zmart_controller

zmart_controller.set_instrument("mock")
```

`set_instrument` takes a driver and connects to its microscope. From then on,
every command goes to that microscope.

The driver can be given in two ways:

- **By name**, from `get_drivers()`. This is how registered drivers are used.
- **As a module**, such as `zmart_controller.mock`. This is handy while you
  write a driver.

Some microscopes need details to connect, such as a host name or an image
folder. Pass them as a **connection dictionary**. The controller hands it to
the driver unchanged.

```python
zmart_controller.set_instrument("mock", {"output_root": "D:/images"})
```

Before connecting, the controller checks that the driver has every required
function. A driver that is missing one is refused by name:

```
ValueError: driver my_driver is missing functions: ['set_xyz']
```

Plugging in a new driver disconnects the previous one. `disconnect()` closes
the connection by hand. To drive several microscopes at once, hold a session
for each. Part 2, [Use the controller](../2_use_the_controller/README.md#several-microscopes-at-once),
shows how.

## Plugin the driver through one python file

The functions the controller calls live in one file,
`zmart_controller_plugin.py`. This files is part of the driver.

```python
# zmart_controller_plugin.py

NAME = "my-scope"
CONNECTION = {"host": "localhost", "output_root": "D:/images"}   # optional

def connect(connection): ...
def get_xyz(handle, *, with_actuators=None): ...
# ... one function per command, as in the table below
```

## The functions

`connect` receives the connection dictionary and returns a **handle**. The
handle is any object that holds the live connection to the microscope. Every
other function receives that handle as its first argument. The controller
never looks inside it.

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
may add keys of its own. It must not leave these out.

The functions

| Function | Receives | `content` must contain |
|---|---|---|
| `connect` | the connection dictionary | *(returns a handle instead)* |
| `disconnect` *(optional)* | handle | *(returns nothing; afterwards every other call raises `RuntimeError`)* |
| `get_info` | handle | `output_root`: the folder where images are saved. Recommended: `description` |
| `get_actuators` | handle | `{axis: [motor names]}` for `x`, `y` and `z`, at least one motor each |
| `get_xyz` | handle, `with_actuators=` | `{axis: {"value", "actuator", "canvas"}}` for `x`, `y` and `z` |
| `set_xyz` | handle, `x`, `y`, `z`, `with_actuators=` | `position` and `actuators`. Raise if the move cannot be confirmed |
| `get_state` | handle | `changeable` and `observed` |
| `set_state` | handle, state | what was applied. Act on `changeable` only |
| `get_acquisition_settings` | handle | `{name: {"options": [...], "active": value}}` |
| `acquire` | handle, `position_label=`, `acquisition_settings=` | `position_label`, `files` and `planes` |
| `get_procedures` | handle | `{name: {"description": ...}}` |
| `run_procedure` | handle, `{"name": ..., ...}` | `ran`: the name of the procedure. Raise `ValueError` for an unknown name |


## What an acquisition reports

`acquire` captures an image at the current position with the current
settings, and saves it. Its `content` holds three things.

| Key | What it is |
|---|---|
| `position_label` | the name the workflow gave this position, such as `"A1"`. The saved files are named after it |
| `files` | the path of every file the acquisition saved: the images, and anything saved beside them, such as a log |
| `planes` | one entry per saved image plane, saying where it sits on the sample |



## State, acquisition settings and description

**The state** is the instrument's settings, captured by `get_state` so they
can be applied again later with `set_state`. It has two parts:

- `changeable`: the settings `set_state` applies, such as laser power or
  exposure time.
- `observed`: a read-only description, such as the objective in place and
  the pixel size. It is never used as an instruction.

**Acquisition settings** are the choices for one acquisition, such as the
file format or the number of planes in a z-stack. `get_acquisition_settings`
lists each one with:

- `options`: the values it may take. When they cannot be listed, a short
  description such as `"number > 0"`.
- `active`: the value used when the setting is left out.

**The description** in `get_info` is the microscope in plain words. It is
read by whoever drives the microscope: a person, a notebook, or the ZMART AI
agent. Say what the other answers cannot: what each setting in `changeable`
means, its unit and its bounds, which objective sits in which slot, and
anything about the sample worth knowing. Leave out what `get_xyz` and
`get_procedures` already report. A driver without a description still works.
When there is one, it must be text with something in it.

Anything else in `get_info` is an extra of your driver. A workflow that
depends on it will not run on other microscopes.

## Rules for every driver

- **Raise when carrying on is unsafe.** `ValueError` when the request is
  wrong: an unknown setting, a position outside the limits. `RuntimeError`
  when the microscope fails. The controller passes the error on unchanged.
- **Report soft outcomes with `success: False`.** Use it only for an outcome
  a workflow can safely carry on from, and say what happened in `content`.
- **Read back to confirm.** Microscope software often accepts a command
  before it has happened. When a setting or an acquisition was sent but never
  showed up, answer `success: False` with `"confirmed": False` and the reason.
  A move is the exception: `set_xyz` raises `RuntimeError`, because carrying
  on at an unknown position is never safe.
- **Reject what you do not understand.** An unknown setting name, acquisition
  setting or procedure raises `ValueError`. A typo that passes silently can cost someone
  an experiment.
- **Keep secrets out of error messages.** The connection dictionary may hold
  passwords. Name the keys, never the values.
- **Keep safety in the driver.** Travel limits, the origin and the
  calibration belong to the driver. The controller checks nothing on the
  microscope's behalf.


## Register a driver

Register a driver once, on the microscope computer. Point the controller at
its `zmart_controller_plugin.py`, or at the folder that holds it:

```python
zmart_controller.register_driver("C:/drivers/my-scope/zmart_controller_plugin.py")
```

`register_driver` imports the file and checks that every function and the
`NAME` are there before it writes anything down. A file that cannot be
imported, or that misses something, is refused with a clear message.

From then on, every Python session on this computer can plug the driver in
by name:

```python
zmart_controller.get_drivers()               # ['mock', 'my-scope']
zmart_controller.set_instrument("my-scope")
```

The mock driver is always on the list. `CONNECTION` is read every time the
driver is plugged in, so after you change it there is nothing to register
again. `remove_driver("my-scope")` takes a driver off the list.

The list is a small file, `drivers.json`, in the configuration folder above.
Everyone who uses the microscope computer sees the same drivers. When that
folder cannot be written, the list is kept in `.zmart-microscopy` in your
home folder instead.

The drivers for the microscopes at the ZMB are in
[ZMART drivers](https://github.com/thomdehoog/ZMART-drivers). Each driver's
README says where its `zmart_controller_plugin.py` is, what goes in its
`CONNECTION`, and how to run its setup step.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
