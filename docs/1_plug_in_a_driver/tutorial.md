# Plug in a driver, step by step

This is a walk-through for someone who would like to connect a microscope to
the ZMART Controller, with no experience of the controller. It plugs in the
mock driver first, looks at what a driver is made of, and then builds a
small driver of your own in a single file. The [README](README.md) is the
complete documentation: every function a driver must have, what each must
answer, and the rules behind them.

## The idea

A workflow written for one microscope does not run on another, because every
microscope software speaks its own language. The controller solves this by
standing in between. Your workflow only ever speaks the controller's short
list of commands, and a **driver** translates each command for one particular
microscope.

```
  your workflow ──► zmart_controller ──► driver ──► vendor software ──► microscope
```

A driver is just **one Python function per command**: `connect`, `get_xyz`,
`set_xyz`, `acquire`, and so on. You hand those functions to the controller,
and the controller calls them. That is all "plugging in" means.

## Before you start

- Python 3.11 or newer.
- A command window: *Terminal* on macOS, *Anaconda Prompt* or *Miniforge
  Prompt* on Windows. It is good practice to work in a Python environment of
  your own, for example one made with conda
  (`conda create -n zmart python=3.12`, then `conda activate zmart`).
- No microscope. Everything here runs on a laptop.

## Step 1: install the controller

```bash
pip install "git+https://github.com/thomdehoog/ZMART-controller"
```

The controller needs nothing beyond Python itself. It comes with the mock
driver, a simulated microscope, so there is nothing else to install.

## Step 2: plug in the mock driver

Open Python (type `python` in the command window) and enter:

```python
import zmart_controller

zmart_controller.set_instrument(zmart_controller.mock)
```

The mock is now connected. Look around:

```python
zmart_controller.get_info()["content"]["description"]
```

This is the microscope in plain words: a pretend widefield fluorescence
microscope with three objectives, a camera of 64 by 64 pixels, and a slide of
small bright spots.

```python
zmart_controller.get_actuators()["content"]
```

`{'x': ['motoric'], 'y': ['motoric'], 'z': ['motoric', 'piezo']}`: the
motors that can move each axis. z has two, a motor for long moves and a piezo
for fine, fast steps.

```python
zmart_controller.set_xyz(100, 50, 0)
answer = zmart_controller.acquire(position_label="A1")
answer["content"]["files"]
```

The stage moved to x = 100 µm, y = 50 µm, and the mock took a picture and
saved it as an OME-TIFF file, which you can open in Fiji or napari. Every
command answered in the same shape, `{"success": ..., "content": ...}`.

```python
zmart_controller.disconnect()
```

Part 2, [Drive the microscope](../2_drive_the_microscope/tutorial.md), goes
through all the commands. Here we look at the other side: the driver.

## Step 3: look at what a driver is

Find the mock driver's folder:

```python
import zmart_controller.mock
zmart_controller.mock.__file__
```

Open the folder it names and look at two files.

**`__init__.py`** lists the functions the controller calls:

```python
zmart_controller.mock.__all__
```

```
['acquire', 'connect', 'disconnect', 'get_acquisition_settings', 'get_actuators',
 'get_info', 'get_procedures', 'get_state', 'get_xyz', 'run_procedure',
 'set_state', 'set_xyz']
```

These twelve names are the whole connection between the controller and a
microscope. `disconnect` is optional; the other eleven are required.

**`driver.py`** holds those functions. Each one is short: it takes the
request, hands it to the parts of the driver below it (moving the stage,
reading back the position, writing the file), and wraps the result as
`{"success": ..., "content": ...}`. The other folders are those parts. A real
microscope needs them, because its software is slow, sometimes busy, and
sometimes wrong. A pretend microscope of your own does not, which is what the
next step shows.

## Step 4: write a driver of your own

Make a file called `pretend_scope.py` in the folder you started Python from,
and copy this into it. It is a complete driver for a microscope that only
exists in memory: it remembers where its stage is and what its exposure is,
and each "picture" is a small text file that says where and how it was
taken.

```python
"""A ZMART driver for a pretend microscope, in one file.

The microscope only exists in memory: it remembers where its stage is and
what its exposure is, and each "picture" is a small text file that says
where and how it was taken.
"""

import json
import tempfile
from pathlib import Path

# How far each axis can travel, in micrometres from the origin.
TRAVEL = {"x": [-1000.0, 1000.0], "y": [-1000.0, 1000.0], "z": [-100.0, 100.0]}
# Half the field of view in x and y. A picture taken at the edge of the travel
# still shows this much further out. This microscope takes no z-stacks, so 0 in z.
HALF_PICTURE = {"x": 50.0, "y": 50.0, "z": 0.0}


def _answer(content, success=True):
    """Wrap the content in the shape every command returns."""
    return {"success": success, "content": content}


def connect(connection):
    """Start the pretend microscope. The handle is a plain dict holding its state."""
    folder = connection.get("output_root") or Path(tempfile.gettempdir()) / "pretend-scope"
    output_root = Path(folder)
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "settings": {"exposure_ms": 10.0},
        "output_root": output_root,
    }


def get_info(handle):
    return _answer(
        {
            "output_root": str(handle["output_root"]),
            "description": "A pretend microscope that lives in memory. One motor per axis; "
            "exposure_ms is the exposure time in milliseconds. +z points towards the objective.",
        }
    )


def get_actuators(handle):
    return _answer({axis: ["motor"] for axis in TRAVEL})


def get_xyz(handle, *, with_actuators=None):
    reading = {}
    for axis, (low, high) in TRAVEL.items():
        reading[axis] = {
            "value": handle["position"][axis],
            "actuator": "motor",
            "unit": "um",
            "range": [low, high],
            "reach": [low - HALF_PICTURE[axis], high + HALF_PICTURE[axis]],
        }
    return _answer(reading)


def set_xyz(handle, x, y, z, *, with_actuators=None):
    target = {"x": x, "y": y, "z": z}
    for axis, value in target.items():
        low, high = TRAVEL[axis]
        if not low <= value <= high:
            raise ValueError(f"{axis} = {value} um is outside the travel, {low} to {high} um")
    handle["position"] = target
    return _answer({"position": dict(target), "actuators": {axis: "motor" for axis in target}})


def get_state(handle):
    return _answer({"changeable": dict(handle["settings"]), "observed": {"objective": "10x"}})


def set_state(handle, state):
    applied = {}
    for name, value in state.get("changeable", {}).items():
        if name not in handle["settings"]:
            raise ValueError(f"unknown setting {name!r}")
        handle["settings"][name] = value
        applied[name] = value
    return _answer({"applied": applied})


def get_acquisition_settings(handle):
    return _answer({"format": {"options": ["json"], "active": "json"}})


def acquire(handle, *, position_label, acquisition_settings=None):
    for name, value in (acquisition_settings or {}).items():
        if name != "format" or value != "json":
            raise ValueError(f"unknown acquisition setting {name!r} = {value!r}")
    path = handle["output_root"] / f"{position_label}.json"
    path.write_text(json.dumps({"position": handle["position"], "settings": handle["settings"]}))
    where = handle["position"]
    plane = {
        "path": str(path),
        "c": 0,
        "z": 0,
        "t": 0,
        "x_um": where["x"],
        "y_um": where["y"],
        "z_um": where["z"],
    }
    return _answer({"position_label": position_label, "files": [str(path)], "planes": [plane]})


def get_procedures(handle):
    return _answer({})


def run_procedure(handle, procedure):
    raise ValueError(f"unknown procedure {procedure.get('name')!r}; this microscope has none")
```

A few things to notice, because a real driver does the same:

- **`connect` returns a handle**, here a plain dictionary. The controller
  never looks inside it; it only hands it back to every other function. A
  real driver keeps its connection to the vendor software in it.
- **`set_xyz` refuses a position outside the travel by raising
  `ValueError`.** It never moves "as far as it can": a workflow that asked for
  somewhere else must hear about it.
- **`acquire` says where it saved the picture** (`files`) and where on the
  sample it was taken (`planes`). That is how a workflow finds its pictures on
  any microscope, without guessing a path.
- **`reach` is the travel widened by half a picture**, because a picture
  taken at the edge of the travel still shows a little beyond it.

## Step 5: plug it in

Start a fresh Python in the same folder and plug in your driver exactly as you
plugged in the mock:

```python
import zmart_controller
import pretend_scope

zmart_controller.set_instrument(pretend_scope)

zmart_controller.set_xyz(100, 50, 0)
answer = zmart_controller.acquire(position_label="A1")
answer["content"]["files"]
```

The list names one file, `A1.json`, in your computer's temporary folder.
Open it: it records the position and the exposure. Now ask for a position
outside the travel:

```python
zmart_controller.set_xyz(5000, 0, 0)
```

```
ValueError: x = 5000 um is outside the travel, -1000.0 to 1000.0 um
```

Your driver refused, and the controller passed the refusal on unchanged.

## Step 6: check that it fits

The controller can check a driver's answers against the requirements:

```python
zmart_controller.validate_driver(pretend_scope)
```

`[]`: an empty list, so every answer has the right shape. `validate_driver`
connects, calls every `get_*` function, and lists any problem in plain words.
It moves nothing and acquires nothing, so check one acquisition separately:

```python
answer = zmart_controller.acquire(position_label="A2")
zmart_controller.check_acquire_answer(answer)
```

`[]` again. To see what a problem looks like, open `pretend_scope.py`, delete
the line with `"reach"` in `get_xyz`, restart Python and validate again:

```
["get_xyz: axis 'x' is missing 'reach'", "get_xyz: axis 'y' is missing 'reach'",
 "get_xyz: axis 'z' is missing 'reach'"]
```

Put the line back. This is the loop to work in when you write a driver: change
a function, validate, read the problems, repeat.

## Step 7: from a pretend microscope to a real one

Your file already works with every workflow, and part 3 builds a workflow on
it. For a real microscope, each function does the same job, but by talking to
the vendor software instead of a dictionary:

- **`connect`** starts or logs into the vendor software, and loads what was
  measured once on this microscope: the origin, the travel limits, the
  calibration. These live on the microscope computer, in the folder that
  `zmart_controller.utils.config_root()` names.
- **`set_xyz`** checks the limits, sends the move, and reads the position back
  until it matches, because microscope software often says "done" before the
  stage has stopped.
- **`acquire`** starts the capture, waits until the vendor's file is complete,
  turns it into OME-TIFF or OME-Zarr lined up with the stage, and reports
  `files` and `planes`.

Once a driver grows beyond one file, make it a package, a folder whose
`__init__.py` imports the functions, exactly as the mock does. The README
section [How a driver is built inside](README.md#how-a-driver-is-built-inside)
and [the anatomy of a ZMART driver](driver-anatomy.md) describe the parts a
real driver is made of; the mock driver is a complete example to copy.

## When something goes wrong

- **`ValueError: driver ... is missing functions: [...]`**: a required
  function is missing or misspelled. The names must match the table in the
  README exactly.
- **`ModuleNotFoundError: No module named 'pretend_scope'`**: Python was
  started in another folder. Start it in the folder that holds
  `pretend_scope.py`.
- **`validate_driver` lists problems**: each sentence names the function and
  what is missing. Fix that function and validate again.
- **An error from your own code**: the controller passes everything your
  driver raises on unchanged, with its own message, so the message points at
  your code.

## Points to be aware of

- **The names are the contract.** The controller finds the functions by name.
  A helper function of your own must not use one of the twelve names.
- **Raise when carrying on is unsafe.** `ValueError` for a request that is
  wrong, `RuntimeError` for a microscope that fails. Use `success: False` only
  for an outcome a workflow can safely carry on from.
- **Positions are micrometres from the origin**, and in a saved picture right
  is +x and down is +y, on every microscope. A real driver turns the vendor's
  own numbers and image orientation into this frame.
- **Never overwrite a picture.** The pretend driver above does, to stay short.
  A real one, like the mock, saves a second acquisition with the same label as
  `A1_001` instead.

## Where to go next

- The [README](README.md): the full requirements for every function.
- Part 2, [Drive the microscope](../2_drive_the_microscope/tutorial.md): every
  command, on the mock.
- Part 3, [Build your workflow](../3_build_your_workflow/tutorial.md): put the
  commands together into an automated workflow.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
