# 1. How do I plug in a ZMART-driver

## Contents

1. [What is a ZMART driver](#1-what-is-a-driver)
2. [Installing a driver](#2-installing-a-driver)
3. [Writing a driver](#3-writing-a-driver)

## 1) What is a ZMART driver

The controller stands in between your workflow and the driver. It knows nothing about any particular workflow or microscope. 
It takes input from your workflow through a short, fixed list of commands and hands these to the driver. You can have multiple workflows and multiple driver, but you only have one controller.

```
your workflow ──► controller ──► driver ──► vendor software ──► microscope
```

A ZMART driver is a folder with at least two files:

- `zmart_driver.json` holds the driver's name, where its ZMART-driver class file is,
  and how to reach the microscope. 
- `zmart_driver.py` holds the `ZmartDriver` class, which integrates the
  code that drives the microscope, one method per command that must comply
  with what the controller needs.
- Optional other tooling for interacting with the microscope

The drivers for the microscopes at the ZMB are in
[ZMART drivers](https://github.com/thomdehoog/ZMART-drivers).

## 2) Installing a ZMART driver

Installing a driver means pointing the controller, once, at the driver's
`zmart_driver.json`:

```python
import zmart_controller

zmart_controller.register_driver("C:/drivers/my-scope/zmart_driver.json")
```

`register_driver` writes the driver into the registry, the file
`C:\ProgramData\zmart-microscopy\zmart-controller\drivers.json` on Windows
(`zmart_controller.registry.registry_file()` names it on any system). From
then on
`get_instruments` recognises the driver, and the controller can connect to
it by name:

```python
zmart_controller.get_instruments()           # {'mock': {}, 'my-scope': {'microscope': ..., 'host': ..., ...}}
mic = zmart_controller.ZmartController("my-scope")
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

`get_instruments()` shows this back for every installed driver.


## 3) Writing a driver

Writing a ZMART driver means expanding the `ZmartDriver` class in
`zmart_driver.py` until it is compatible with the following schema. This is
what the controller offers to a workflow; every command on it becomes a
call to the method of the same name on your class.

```python
import zmart_controller

The mock driver is always on the list, and the name `"mock"` is taken.
# 1) See which drivers are installed and how each connects, then connect to one
zmart_controller.get_instruments()
mic = zmart_controller.ZmartController("my-scope")

# 2) Learn about the connected setup: where images go, and the microscope in plain words
mic.get_info()

# 3) Discover the motors, then read the position and where pictures can show, or move (micrometres)
mic.get_actuators()
mic.get_xyz()
mic.set_xyz(x, y, z, with_actuators=Dict)

# 4) Capture the instrument settings, and apply them again later
mic.get_state()
mic.set_state(Dict)

# 5) Capture and save an image with the current settings and position
mic.get_acquisition_settings()
mic.acquire(position_label=String, acquisition_settings=Dict)

# 6) Run a routine the microscope offers (for example autofocus)
mic.get_procedures()
mic.run_procedure(Dict)

# 7) Close the connection
mic.disconnect()
```

Every command answers in the same shape, built from what your method
hands back.

| Your method | The answer |
|---|---|
| hands back `True` and the values | `{"success": True, "content": {...}}`, the values under fixed keys |
| hands back `False` and a message | `{"success": False, "content": "..."}`, your message |
| raises | `{"success": False, "content": "..."}`, the error text |

So what is left for you is the methods. Making a `ZmartDriver` opens the
connection, and each method does one command. Every method starts out
raising `NotImplementedError`. While you write, one call tells you which
methods still hand back the wrong thing, one plain sentence each, and an
empty list means the driver fits:

```python
zmart_controller.validate_driver("C:/drivers/my-scope/zmart_driver.json")
```

### Connect and disconnect

```python
def __init__(self, connection): ...
def disconnect(self): ...
```

`connection` is the dictionary from `zmart_driver.json`. Open the vendor
software with it and keep what you need on `self`. Load here, too, what was
measured once for this microscope, the origin, the travel limits and the
calibration. Keep those in the folder `zmart_controller.registry.config_root()`
names, `C:\ProgramData\zmart-microscopy` on Windows, so every user finds
them.

### Describe the microscope

```python
def get_info(self): ...            # True, (output_root, description)
```

`output_root` is the folder where images are saved. `description` is the
microscope in plain words, for whoever drives it: what each setting means,
its unit and its bounds, which objective sits in which slot, and which way
+z points.

### Position

```python
def get_actuators(self): ...                       # True, (x_motors, y_motors, z_motors)
def get_xyz(self, with_actuators): ...             # True, (x, y, z, x_motor, y_motor, z_motor, canvas)
def set_xyz(self, x, y, z, with_actuators): ...    # moves; True, (x_motor, y_motor, z_motor)
```

Positions are micrometres from the origin, a point saved once for this
microscope, so that a position means the same place on the sample every
time. In a saved image, right is +x and down is +y, on every microscope.
Turning the vendor's own numbers into this frame is the driver's job.

Each axis has one or more motors; `get_actuators` names them.
`with_actuators` picks one per axis, such as `{"z": "piezo"}`, or is `None`
for the first one. The canvas, `(x_min, x_max, y_min, y_max, z_min, z_max)`,
is the travel widened by half a field of view: everywhere a picture can
show. `set_xyz` checks the limits, moves, and reads back until the stage
has arrived; when it never does, hand back `False` and say where it is.

### Settings

```python
def get_state(self): ...               # True, (changeable, observed)
def set_state(self, changeable): ...   # applies them; True, applied
```

`changeable` holds the settings `set_state` can apply, such as exposure
time. `observed` describes what can only be read, such as the objective in
place. Both are dictionaries. `set_state` reads each setting back to
confirm it took, and returns what it applied.

### Acquire

```python
def get_acquisition_settings(self): ...                        # True, {name: {"options": [...], "active": value}}
def acquire(self, position_label, acquisition_settings): ...   # captures and saves; True, (files, planes)
```

Acquisition settings are the choices for one picture, such as the file
format. `options` lists what a setting may be, and `active` is what is used
when it is left out. `acquire` captures at the current position, saves the
files named after `position_label`, and returns `files`, the path of every
file saved, and `planes`, one entry per image plane:
`{"path", "c", "z", "t", "x_um", "y_um", "z_um"}`, with `c`, `z` and `t`
counted from 0 and the stage position in micrometres. Never overwrite an
earlier picture.

### Procedures

```python
def get_procedures(self): ...             # True, {name: {"description": ...}}
def run_procedure(self, procedure): ...   # runs the one named procedure["name"]; True, name
```

Procedures are the routines the microscope offers, such as autofocus.
`procedure` holds the name and the arguments. A name that is not listed
raises `ValueError`.

In every method, raise `ValueError` for a request that is wrong, such as
an unknown setting or a position outside the travel, and hand back `False`
with a message when the microscope did not do what was asked. Never put a
password in a message.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
