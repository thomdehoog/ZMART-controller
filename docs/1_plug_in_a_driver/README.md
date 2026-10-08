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

`ZmartDriver` in `zmart_driver.py` is the code that drives the vendor
software. Making one opens the connection; each method does one command.
Every method starts out raising `NotImplementedError`, so `validate_driver`
tells you which one is still to write. Each returns plain values; the
controller wraps them.

```python
class ZmartDriver:
    def __init__(self, connection): ...                             # open the vendor connection, keep what you need on self
    def disconnect(self): ...                                       # close it

    def get_info(self): ...                                         # returns output_root, description
    def get_actuators(self): ...                                    # returns x_motors, y_motors, z_motors
    def get_xyz(self, with_actuators): ...                          # returns x, y, z, x_motor, y_motor, z_motor
    def get_canvas(self): ...                                       # returns x_min, x_max, y_min, y_max, z_min, z_max
    def set_xyz(self, x, y, z, with_actuators): ...                 # moves, returns x_motor, y_motor, z_motor
    def get_state(self): ...                                        # returns changeable, observed
    def set_state(self, changeable): ...                            # applies them, returns applied
    def get_acquisition_settings(self): ...                         # returns {name: {"options": [...], "active": value}}
    def acquire(self, position_label, acquisition_settings): ...    # captures and saves, returns files, planes
    def get_procedures(self): ...                                   # returns {name: {"description": ...}}
    def run_procedure(self, procedure): ...                         # runs the one named procedure["name"]
```

What the values mean:

| Value | Meaning |
|---|---|
| `connection` | the dictionary from `zmart_driver.json`. Also load here what was measured once for this microscope: origin, travel limits, calibration, from the [configuration folder](#the-configuration-folder) |
| `output_root` | the folder where images are saved |
| `description` | the microscope in plain words, for whoever drives it: what each changeable setting means, its unit and bounds, which objective is in which slot, which way +z points |
| `x_motors`, `y_motors`, `z_motors` | the motor names that can move each axis, at least one each |
| `with_actuators` | `{"z": "piezo"}` or `None`: the motor to use per axis. Left out, the first one. Unknown name: raise `ValueError` |
| `x`, `y`, `z` | micrometres from the origin, the point saved once for this microscope. In a saved image, right is +x and down is +y |
| `x_min` ... `z_max` | the canvas: the travel widened by half a field of view, everywhere a picture can show |
| `changeable`, `observed` | two dictionaries: the settings `set_state` applies, and a read-only description such as the objective in place |
| `applied` | the settings that were changed |
| `options`, `active` | the values a setting may take, or a description such as `"number > 0"`, and the value used when left out |
| `files` | the path of every file the acquisition saved. Never overwrite an earlier one |
| `planes` | one entry per saved image plane: `{"path", "c", "z", "t", "x_um", "y_um", "z_um"}`, counts from 0, position in micrometres or `None` |
| `procedure` | `{"name": ..., ...}`: the routine to run and its arguments. Unknown name: raise `ValueError` |

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
