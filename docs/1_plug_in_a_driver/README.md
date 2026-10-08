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

Writing a ZMART driver means filling in the methods of the `ZmartDriver`
class in `zmart_driver.py`. Every command a workflow gives the controller
becomes a call to the method of the same name on your class.

These are the methods that need to be filled in:

```python
class ZmartDriver:
    def __init__(self, connection): ...
    def disconnect(self): ...

    def get_info(self): ...
    def get_actuators(self): ...
    def get_xyz(self, with_actuators): ...
    def set_xyz(self, x, y, z, with_actuators): ...
    def get_state(self): ...
    def set_state(self, changeable): ...
    def get_acquisition_settings(self): ...
    def acquire(self, position_label, acquisition_settings): ...
    def get_procedures(self): ...
    def run_procedure(self, procedure): ...
```

### General rules

Input: the arguments the workflow gave the command, unchanged. `connection`
is the dictionary from `zmart_driver.json`.

Output: a pair. `True` and the values when the microscope did what was
asked, or `False` and a message saying why not. The controller turns that
into the answer the workflow sees:

| Your method | The answer |
|---|---|
| `True, values` | `{"success": True, "content": {...}}`, the values under fixed keys |
| `False, message` | `{"success": False, "content": message}` |
| raises | `{"success": False, "content": "<the error text>"}` |

Raise `ValueError` for a request that is wrong, such as an unknown setting
or a position outside the travel. Positions are micrometres from the
origin saved for this microscope; in a saved image, right is +x and down
is +y.

While you write, one call tells you which methods still hand back the
wrong thing, one plain sentence each; an empty list means the driver fits:

```python
zmart_controller.validate_driver("C:/drivers/my-scope/zmart_driver.json")
```

### Per call

| Method | Hands back |
|---|---|
| `__init__(connection)` | nothing; opens the vendor connection and keeps what you need on `self` |
| `disconnect()` | nothing; closes it |
| `get_info()` | `output_root`, the folder where images are saved, and `description`, the microscope in plain words |
| `get_actuators()` | `x_motors, y_motors, z_motors`: the motor names per axis, at least one each |
| `get_xyz(with_actuators)` | `x, y, z, x_motor, y_motor, z_motor, canvas`; `canvas` is `(x_min, x_max, y_min, y_max, z_min, z_max)`, the travel widened by half a field of view |
| `set_xyz(x, y, z, with_actuators)` | `x_motor, y_motor, z_motor` once the stage has arrived; `False` and where it is when it never does |
| `get_state()` | `changeable`, the settings `set_state` can apply, and `observed`, what can only be read; two dictionaries |
| `set_state(changeable)` | `applied`, the settings that took; `False` and which did not |
| `get_acquisition_settings()` | `{name: {"options": [...], "active": value}}` |
| `acquire(position_label, acquisition_settings)` | `files`, the path of every file saved, and `planes`, one entry per image plane: `{"path", "c", "z", "t", "x_um", "y_um", "z_um"}` |
| `get_procedures()` | `{name: {"description": ...}}` |
| `run_procedure(procedure)` | the name that ran; `procedure["name"]` picks it, the other keys are its arguments |

`with_actuators` picks a motor per axis, such as `{"z": "piezo"}`, or is
`None` for the first one. The docstring of each method in the template
says the rest.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
