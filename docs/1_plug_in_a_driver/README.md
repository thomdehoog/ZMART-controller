# 1. How do I plug in a ZMART-driver

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


## 3) Writing a driver

Fill in the methods of the `ZmartDriver` class in `zmart_driver.py`. Each
command a workflow gives the controller calls the method of the same name.

### Input and output

A method hands back `True` and the values, or `False` and a message. The
controller turns that into the answer the workflow sees:

```python
def set_state(self, changeable):
    ...
    return True, applied                     # {"success": True,  "content": {"applied": applied}}
    return False, "exposure_ms stayed 10.0"  # {"success": False, "content": "exposure_ms stayed 10.0"}
    raise ValueError("unknown setting")      # {"success": False, "content": "ValueError: unknown setting"}
```

```python
zmart_controller.validate_driver("C:/drivers/my-scope/zmart_driver.json")   # [] when every method fits
```

### Per call

```python
class ZmartDriver:
    def __init__(self, connection): ...                            # connection: the dict from zmart_driver.json
    def disconnect(self): ...

    def get_info(self): ...                                        # True, (output_root, description)
    def get_actuators(self): ...                                   # True, (x_motors, y_motors, z_motors)
    def get_xyz(self, with_actuators): ...                         # True, (x, y, z, x_motor, y_motor, z_motor, canvas)
    def set_xyz(self, x, y, z, with_actuators): ...                # True, (x_motor, y_motor, z_motor)
    def get_state(self): ...                                       # True, (changeable, observed)
    def set_state(self, changeable): ...                           # True, applied
    def get_acquisition_settings(self): ...                        # True, {name: {"options": [...], "active": value}}
    def acquire(self, position_label, acquisition_settings): ...   # True, (files, planes)
    def get_procedures(self): ...                                  # True, {name: {"description": ...}}
    def run_procedure(self, procedure): ...                        # True, procedure["name"]
```

```python
x, y, z          # micrometres from the saved origin; in a saved image, right is +x and down is +y
with_actuators   # {"z": "piezo"} or None for the first motor
canvas           # (x_min, x_max, y_min, y_max, z_min, z_max): the travel plus half a field of view
changeable       # {"exposure_ms": 10.0, ...}: the settings set_state can apply
observed         # {"objective": "10x", ...}: what can only be read
files            # ["D:/images/A1.ome.tif", ...]: every file saved
planes           # [{"path": ..., "c": 0, "z": 0, "t": 0, "x_um": ..., "y_um": ..., "z_um": ...}, ...]
procedure        # {"name": "autofocus", ...}: the routine and its arguments
```

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
