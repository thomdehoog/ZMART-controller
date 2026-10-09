# How do I plug in a ZMART-driver

## Contents

1. [What is a ZMART driver](#1-what-is-a-zmart-driver)
2. [Installing a ZMART driver](#2-installing-a-zmart-driver)
3. [Writing a driver](#3-writing-a-driver)

## 1) What is a ZMART driver

The controller stands in between your workflow and the driver. It knows nothing about any particular workflow or microscope. 
It takes input from your workflow through a short, fixed list of commands and hands these to the driver. You can have multiple workflows and multiple drivers, but you only have one controller.

```
your workflow ──► controller ──► driver ──► vendor software ──► microscope
```

A ZMART driver is a folder with at least two files:

- `zmart_driver.json` holds the driver's name, where its ZMART-driver class file is,
  and how to reach the microscope. 
- `zmart_driver.py` holds the `ZmartDriver` class, which integrates the
  code that drives the microscope, one method per command that must comply
  with what the ZMART controller needs.
- Optional other tooling for interacting with the microscope

The drivers for the microscopes at the ZMB are in
the [ZMART drivers](https://github.com/thomdehoog/ZMART-drivers) repository.

## 2) Installing a ZMART driver

Installing a driver means pointing the controller at the driver's
`zmart_driver.json`:

```python
from zmart_controller import mic

mic.register_driver("C:/drivers/my-scope/zmart_driver.json")
```

`register_driver` writes the driver into the registry, the file
`C:\ProgramData\zmart-microscopy\zmart-controller\drivers.json` on Windows
(`zmart_controller.registry.registry_file()` names it on any system). From
then on
`get_instruments` recognises the driver, and the controller can connect to
it by name:

```python
mic.get_instruments()                        # {'mock': {}, 'my-scope': {'microscope': ..., 'host': ..., ...}}
mic.connect("my-scope")
```

`get_instruments` lists every installed driver with how it connects,
without its password.

The zmart_driver.json is formatted in the following way: 

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


## 3) Writing a driver

Open `zmart_driver.py` and fill in the methods of the `ZmartDriver` class.
There is one method per command. When a workflow calls `mic.set_state(...)`,
the controller calls your `set_state(...)`, and so on for every command.

### Input and output

Each method returns two things: `True` and the output, or `False` and an
error message. The controller turns this into the answer the workflow sees,
with the keys `success` and `content`. If the method raises an error instead,
for example because the vendor library failed, the controller catches it and
answers `False` with the text of the error:

```python
def set_state(self, changeable):
    ...
    return True, applied                     # {"success": True,  "content": {"applied": applied}}
    return False, "<error message>"          # {"success": False, "content": "<error message>"}
    raise ValueError("unknown setting")      # anything that raises: {"success": False, "content": "ValueError: unknown setting"}
```

Apply only what is under `changeable`. Read each setting back to confirm
it took; a setting the microscope does not have is a failure.

### Per call

#### __init__

```python
def __init__(self, connection):
    # connection: the dict from zmart_driver.json
    # open the vendor software with it; keep what you need on self
    # load what was measured once for this microscope: origin, travel limits, calibration
```

This runs when the controller connects. Open the vendor software with the
details in `connection`. Then load what was measured once for this
microscope: the origin, the travel limits and the calibration. Every later
command uses them to work in the sample's coordinate system.

#### disconnect

```python
def disconnect(self):
    # close the vendor connection
```

Close the connection to the vendor software, so that it can be opened again later.

#### get_info

```python
def get_info(self):
    return True, description
    # the microscope in plain words: each setting, its unit and bounds, the objectives, which way +z points
```

The description is read by the person or the program that drives the
microscope. Write what the other commands cannot tell: what each setting
means, its unit and its limits, which objective is in which slot, and which
way +z points.

#### get_actuators

```python
def get_actuators(self):
    return True, (x_motors, y_motors, z_motors)
    # the motor names per axis, at least one each, e.g. ["motoric", "piezo"]
```

List every motor that can move each axis. The first motor in the list is
the default when a command does not choose one.

#### get_xyz

```python
def get_xyz(self, with_actuators):
    # with_actuators: {"z": "piezo"} or None for the first motor of each axis
    return True, (x, y, z, actuators, canvas)
    # x, y, z:   micrometres from the saved origin; in a saved image, right is +x and down is +y
    # actuators: {"x": {"motoric": 50000.0}, "y": {...}, "z": {"motoric": 5000.0, "piezo": 0.0}}:
    #            every motor of each axis with its own raw reading, as the microscope reports it
    # canvas:    (x_min, x_max, y_min, y_max, z_min, z_max): the travel plus half a field of view
```

Read the stage position and return it in the sample's coordinate system.
That is micrometres from the saved origin, where right is +x and down is +y
in a saved image. Under `actuators`, return every motor of each axis with
its raw reading, exactly as the microscope reports it. Do not subtract the
origin and do not convert. The `canvas` is the range where an image can be
taken: the stage travel plus half a field of view.

The controller turns this into the answer the workflow sees. There is one
entry per axis with `position`, `unit`, `actuators` and `canvas`:

```python
{"x": {"position": 0.0, "unit": "micrometer", "actuators": {"motoric": 50000.0}, "canvas": [-5032.0, 5032.0]}, "y": {...}, "z": {...}}
```

#### set_xyz

```python
def set_xyz(self, x, y, z, with_actuators):
    # move, then read back until the stage has arrived
    return self.get_xyz(with_actuators)            # the same True, (x, y, z, actuators, canvas) as get_xyz
    return False, "<error message>"                # e.g. outside the travel, or the stage never arrived
```

Move to a position in the sample's coordinate system. Check the travel
limits first. Then move, and read the position back until the stage has
arrived. Return the same answer as `get_xyz`, read from the microscope. The
workflow then sees the real position, not the one it asked for. If the
stage never arrives, return `False` with a message, so that the workflow
stops.

#### get_state

```python
def get_state(self):
    return True, (changeable, observed)
    # changeable: {"exposure_ms": 10.0, ...}: the settings set_state can apply
    # observed:   {"objective": "10x", ...}: what can only be read
```

Return the current settings in two parts. `changeable` holds the settings
that `set_state` can change. `observed` holds facts that can only be read,
such as the objective in use. Only `changeable` is ever sent back to
`set_state`.

#### set_state

```python
def set_state(self, changeable):
    # apply each one, then read it back
    return True, applied                           # {"exposure_ms": 20.0, ...}: what took
    return False, "<error message>"                # e.g. a setting that did not take, or an unknown one
```

#### get_acquisition_settings

```python
def get_acquisition_settings(self):
    return True, {name: {"options": [...], "active": value}}
    # options: the values a setting may take, or a description such as "number > 0"
    # active: the value used when the setting is left out of acquire
```

List the settings for taking one image, such as the file format or the
number of planes in a z-stack. For each setting, give the values it can take
and the value in use.

#### acquire

```python
def acquire(self, position_label, acquisition_settings):
    # capture here, save the files named after position_label; never overwrite an earlier one
    return True, (files, planes)
    # files:  ["D:/images/A1.ome.tif", ...]: every file saved
    # planes: [{"path": ..., "c": 0, "z": 0, "t": 0, "x_um": ..., "y_um": ..., "z_um": ...}, ...]
```

Take an image at the current position with the current settings, and save
it. Return every saved file in `files`. Return every image plane in
`planes`, with its stage position in the sample's coordinate system. This
way a workflow finds its images in the same way on every microscope. Never
overwrite an earlier image: save a second image with the same label under
a new name.

#### get_procedures

```python
def get_procedures(self):
    return True, {name: {"description": ...}}
    # the routines the microscope offers, such as autofocus
```

List the routines this microscope offers, such as autofocus. Give each one
a description that says what it does, which options it takes, and their
defaults.

#### run_procedure

```python
def run_procedure(self, procedure):
    # procedure: {"name": "autofocus", ...}: the routine and its arguments
    return True, procedure["name"]
    return False, "<error message>"                # e.g. a name that get_procedures does not list
```

Run the routine named in `procedure`. The other keys are its options. A
name that `get_procedures` does not list is a failure.

```python
mic.validate_driver("C:/drivers/my-scope/zmart_driver.json")   # [] when every method fits
```

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.

If the code in this repository inspires you, or you use it or build on it, please acknowledge it.
The [CITATION.cff](../../CITATION.cff) file says how to cite it.
