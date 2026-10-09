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

Apply only the settings under `changeable`. Read each one back to check
that it was applied. A setting the microscope does not have is a failure.

### Per call

Each block shows the method as the controller calls it, and what it must return. The comments are the contract.

<br>

#### __init__

```python
def __init__(self, connection):
    # connection: the "connection" dict from zmart_driver.json
    # open the vendor software and keep what you need on self
    # load the origin, the travel limits and the calibration of this microscope
```

<br>

#### disconnect

```python
def disconnect(self):
    # close the connection to the vendor software
```

<br>

#### get_info

```python
def get_info(self):
    return True, description
    # description: a text for the person or program driving the microscope:
    #              what each setting means, its unit and limits, the objectives, which way +z points
```

<br>

#### get_actuators

```python
def get_actuators(self):
    return True, (x_motors, y_motors, z_motors)
    # the motor names per axis, for example ["motoric", "piezo"]; the first one is the default
```

<br>

#### get_xyz

```python
def get_xyz(self, with_actuators):
    # with_actuators: {"z": "piezo"} or None for the first motor of each axis
    return True, (x, y, z, actuators, canvas)
    # x, y, z:   micrometres from the origin; in a saved image, right is +x and down is +y
    # actuators: {"x": {"motoric": 50000.0}, "y": {...}, "z": {"motoric": 5000.0, "piezo": 0.0}}
    #            the raw reading of every motor, as the microscope reports it
    # canvas:    (x_min, x_max, y_min, y_max, z_min, z_max): the travel plus half a field of view
```

<br>

#### set_xyz

```python
def set_xyz(self, x, y, z, with_actuators):
    # check the travel limits, move, then read back until the stage has arrived
    return self.get_xyz(with_actuators)            # the same answer as get_xyz
    return False, "<error message>"                # outside the travel, or the stage never arrived
```

<br>

#### get_state

```python
def get_state(self):
    return True, (changeable, observed)
    # changeable: {"exposure_ms": 10.0, ...}: the settings set_state can change
    # observed:   {"objective": "10x", ...}: facts that can only be read
```

<br>

#### set_state

```python
def set_state(self, changeable):
    # apply each setting, then read it back
    return True, applied                           # {"exposure_ms": 20.0, ...}: what was applied
    return False, "<error message>"                # a setting that did not take, or an unknown one
```

<br>

#### get_acquisition_settings

```python
def get_acquisition_settings(self):
    return True, {name: {"options": [...], "active": value}}
    # options: the values a setting can take, or a description such as "number > 0"
    # active:  the value used when acquire is called without it
```

<br>

#### acquire

```python
def acquire(self, position_label, acquisition_settings):
    # take an image here and save it under position_label; never overwrite an earlier file
    return True, (files, planes)
    # files:  ["D:/images/A1.ome.tif", ...]: every saved file
    # planes: [{"path": ..., "c": 0, "z": 0, "t": 0, "x_um": ..., "y_um": ..., "z_um": ...}, ...]
```

<br>

#### get_procedures

```python
def get_procedures(self):
    return True, {name: {"description": ...}}
    # the routines this microscope offers, such as autofocus; the description names the options and their defaults
```

<br>

#### run_procedure

```python
def run_procedure(self, procedure):
    # procedure: {"name": "autofocus", ...}: the routine and its options
    return True, procedure["name"]
    return False, "<error message>"                # a name that get_procedures does not list
```

<br>

### Check your driver

```python
mic.validate_driver("C:/drivers/my-scope/zmart_driver.json")   # [] when every method fits
```

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.

If the code in this repository inspires you, or you use it or build on it, please acknowledge it.
The [CITATION.cff](../../CITATION.cff) file says how to cite it.
