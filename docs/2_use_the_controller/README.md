# 2. Use the controller

Every command of the ZMART Controller, for the person who drives the
microscope.

This page is the reference. For a step-by-step walk-through, open the
[tutorial notebook](tutorial.ipynb).

Every example runs on the mock driver, the simulated microscope that comes
with the controller. The outputs are real answers from it, trimmed where they
are long. On another microscope the numbers differ. The shape of every answer
is the same.

## Contents

1. [The idea](#the-idea)
2. [Plug in and disconnect](#plug-in-and-disconnect)
3. [Every answer has the same shape](#every-answer-has-the-same-shape)
4. [Learn about the setup](#learn-about-the-setup-get_info)
5. [Position](#position-get_actuators-get_xyz-set_xyz)
6. [Settings](#settings-get_state-set_state)
7. [Acquire](#acquire-get_acquisition_settings-acquire)
8. [Procedures](#procedures-get_procedures-run_procedure)
9. [When something goes wrong](#when-something-goes-wrong)
10. [Several microscopes at once](#several-microscopes-at-once)
11. [What works on every microscope](#what-works-on-every-microscope)
12. [All commands at a glance](#all-commands-at-a-glance)

## The idea

The controller offers a short, fixed list of commands: plug in a microscope,
learn about it, move, read and apply settings, acquire, run a routine such as
autofocus, and disconnect. You send the commands. The driver of the connected
microscope carries them out and answers.

```
your script ──► zmart_controller ──► driver ──► microscope
            ◄── {"success", "content"} ◄──
```

The controller does no microscope work itself. It hands each command to the
driver and gives you the driver's answer unchanged. Every check, such as
whether a position is inside the travel limits, happens in the driver. Only
the driver knows the hardware.

Every command waits until the driver has finished. When `set_xyz` returns,
the stage has arrived. When `acquire` returns, the files are saved.

## Plug in and disconnect

```python
import zmart_controller

zmart_controller.get_drivers()
```
```
['mock']
```

`get_drivers()` lists the drivers installed on this computer. The mock
driver is always there. `get_instruments()` lists the same drivers with how
each one connects to its microscope, such as the host, without passwords.
Part 1 explains how to install the driver of a real microscope.

```python
zmart_controller.set_instrument("mock")
```

`set_instrument(driver, connection=None)` plugs in a driver and connects to
its microscope. Every command you call afterwards goes to it.

- `driver` is a name from `get_drivers()`. It can also be the driver module
  itself, such as `zmart_controller.mock`.
- `connection` is an optional dictionary that is handed to the driver
  unchanged. It holds whatever that driver needs to connect. Each driver's
  README says what it accepts. Left out, the driver's own configuration is
  used.

The mock accepts three entries:

| Entry | What it does |
|---|---|
| `output_root` | the folder for its images. Default: a folder in your computer's temporary space |
| `mock_timing` | `"realistic"` (default) or `"instant"`, for quick tests |
| `token` | its pretend login |

```python
zmart_controller.set_instrument("mock", {"output_root": "my_images"})
```

If the driver is missing a function the controller needs, `set_instrument`
refuses it with a `ValueError` before anything connects.

Plugging in a second microscope disconnects the first. To close the
connection yourself:

```python
zmart_controller.disconnect()
```

Afterwards every command raises an error until `set_instrument` is called
again. Calling `disconnect` twice is harmless.

Two things to know about this short style:

- **Call through the module each time**, as in `zmart_controller.set_xyz(...)`.
  A command saved in a variable keeps pointing at the old microscope after
  you plug in another one.
- **It assumes one thread.** For several threads, give each its own `ZmartController`
  (see [Several microscopes at once](#several-microscopes-at-once)).

## Every answer has the same shape

Every command except `disconnect` answers with a dictionary of two things:

```python
{"success": True, "content": {...}}
```

- `success` says whether the driver did what you asked.
- `content` is what the driver has to say: a position, a list of saved
  files, a state.

`success: False` means the outcome is safe to carry on from, but not what you
asked for. The reason is in `content`. Anything that is not safe to carry on
from is raised as an error instead. See
[When something goes wrong](#when-something-goes-wrong).

## Learn about the setup: get_info

```python
zmart_controller.get_info()["content"]
```
```
{'output_root': '/tmp/zmart-mock-output',
 'description': 'A pretend widefield fluorescence microscope that runs
   entirely in software (MockScope Control) ...',
 'serial': 'MOCK-0001',
 ...}
```

Two keys are the same on every microscope:

- `output_root` is the folder where the driver saves images.
- `description` is the microscope in plain words: what each setting means,
  its unit and its bounds, which objective sits in which slot. Read it once
  when you meet a new microscope.

Everything else in `get_info`, such as the mock's `serial`, is an extra of
that driver.

## Position: get_actuators, get_xyz, set_xyz

### The coordinates

Positions are in **micrometres from the origin**. The origin is a point
(0, 0, 0) that was chosen and saved once for this microscope. So a position
means the same place on the sample every time you connect.

Positions and pictures share one frame. **In a saved image, right is +x and
down is +y.** A picture taken further along +x shows what lay to the right.
This holds on every microscope. Which way +z points is the microscope's own.
The driver says so in its `description`.

### get_xyz

```python
zmart_controller.get_xyz()["content"]
```
```
{'x': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-5032.0, 5032.0]},
 'y': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-5032.0, 5032.0]},
 'z': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-500.0, 500.0]}}
```

For each axis:

| Key | What it is |
|---|---|
| `value` | where the axis is now |
| `actuator` | the motor that was read |
| `canvas` | `[min, max]`: everywhere a picture can show on that axis |

The canvas is the stage's travel, widened by half a field of view. A picture
taken at the edge of the travel still shows half a field beyond it. On the
mock, the field is 64 µm wide, so the canvas reaches 32 µm past the travel.
The viewer uses the canvas to lay out the whole specimen area before the
first picture arrives. Plan your positions half a field inside it. The stage
itself stops at the travel limits.

### get_actuators and with_actuators

Some axes have more than one motor. On the mock, z has a coarse `"motoric"`
drive for long moves and a `"piezo"` for fine, fast steps.

```python
zmart_controller.get_actuators()["content"]
```
```
{'x': ['motoric'], 'y': ['motoric'], 'z': ['motoric', 'piezo']}
```

Name the motor you want per axis with `with_actuators`, on both `get_xyz`
and `set_xyz`. Axes you leave out use the first motor in the list.

```python
zmart_controller.get_xyz(with_actuators={"z": "piezo"})["content"]["z"]["actuator"]
```
```
'piezo'
```

### set_xyz

```python
zmart_controller.set_xyz(100, 50, 0)["content"]
```
```
{'position': {'x': 100, 'y': 50, 'z': 0},
 'readback': {'x': 100.0, 'y': 50.0, 'z': 0.0},
 'actuators': {'x': 'motoric', 'y': 'motoric', 'z': 'motoric'}}
```

`set_xyz(x, y, z, with_actuators=None)` moves to a position in micrometres
from the origin. All three axes are always given, so a script always says
exactly where it wants to be. The answer names the position and the motors
used. The mock adds `readback`, the position it read after the move.

A move outside the travel is refused with `ValueError` before anything
moves:

```python
zmart_controller.set_xyz(99999, 0, 0)
```
```
ValueError: move refused: x would go to 149999.00 µm (stage coordinates),
outside the travel range [45000.0, 55000.0] set in the limits
```

The message counts in the stage's own coordinates, where the limits are set.
Those numbers differ from yours by the origin.

A move the driver cannot confirm raises `RuntimeError`, because carrying on
at an unknown position is never safe.

## Settings: get_state, set_state

A *state* is a snapshot of the microscope's settings: everything that decides
what an image looks like, such as the objective, laser power and exposure.

```python
zmart_controller.get_state()["content"]
```
```
{'changeable': {'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0, 'objective': 1},
 'observed': {'objective': '10x/0.30 Air',
              'pixel_size': {'x': 1.0, 'y': 1.0, 'unit': 'um'},
              ...}}
```

It has two parts:

- `changeable` holds the settings that `set_state` can apply. Which settings
  there are is the microscope's own. The `description` from `get_info`
  explains them.
- `observed` describes the microscope as it is, such as the objective's name
  and the pixel size. It is for reading only. `set_state` never acts on it.

The usual way to work: capture a state, change what you need, and apply it.

```python
overview = zmart_controller.get_state()["content"]
overview["changeable"]["laser_power"] = 20.0

zmart_controller.set_state(overview)["content"]
```
```
{'applied': {'objective': 1, 'laser_power': 20.0, 'gain': 100.0, 'exposure_ms': 10.0},
 'unconfirmed': {}}
```

You can also apply only a few settings. The rest stay as they are.

```python
zmart_controller.set_state({"changeable": {"gain": 200.0}})["content"]
```
```
{'applied': {'gain': 200.0}, 'unconfirmed': {}}
```

A value outside the microscope's limits is refused with `ValueError`. When a
setting was sent but the microscope never showed it, the answer is
`success: False`. The mock then lists that setting under `unconfirmed`, with
the reason. A setting name the microscope does not know is refused with
`ValueError` before anything is applied, so a typo never passes silently.

A state is a plain dictionary. Save it to a file with `json`, and apply it
again on another day.

## Acquire: get_acquisition_settings, acquire

### get_acquisition_settings

Acquisition settings are the choices about *how* to capture and save, as
opposed to the microscope's settings in the state. Each driver offers its
own. For each one, `options` says what values it may take and `active` which
value is used when you say nothing.

```python
zmart_controller.get_acquisition_settings()["content"]
```
```
{'folder': {'options': 'any text; empty saves straight into output_root', 'active': ''},
 'backlash_correction': {'options': [True, False], 'active': True},
 'format': {'options': ['ome-tiff', 'ome-zarr'], 'active': 'ome-tiff'},
 'z_planes': {'options': 'whole number from 1 up to the limit', 'active': 1},
 'z_step_um': {'options': 'number > 0', 'active': 1.0}}
```

On the mock:

| Setting | What it does |
|---|---|
| `folder` | saves the files in a folder of that name under `output_root` |
| `backlash_correction` | approaches every position from the same side, so positions repeat exactly |
| `format` | OME-TIFF (one file per plane) or OME-Zarr (one folder for the whole acquisition) |
| `z_planes`, `z_step_um` | a z-stack: that many planes, that far apart in micrometres |

### acquire

```python
answer = zmart_controller.acquire(position_label="A1")
answer["content"]
```
```
{'position_label': 'A1',
 'files': ['/tmp/zmart-mock-output/A1.ome.tif',
           '/tmp/zmart-mock-output/A1.commands.json'],
 'planes': [{'path': '/tmp/zmart-mock-output/A1.ome.tif',
             'c': 0, 'z': 0, 't': 0,
             'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}],
 'position': {'x': 100.0, 'y': 50.0, 'z': 0.0},
 'confirmed': True,
 ...}
```

`acquire(position_label, acquisition_settings=None)` captures an image with
the current settings at the current position, and saves it, in one step.

- `position_label` names this position in the saved files, such as `"A1"`.
  It is required. A second acquisition with the same label never overwrites
  the first. The mock saves it as `A1_001`, then `A1_002`, and so on.
- `acquisition_settings` holds choices from `get_acquisition_settings`. Any
  you leave out keep their active value. An unknown name is refused with
  `ValueError`, so a typo never passes silently.

Three keys of the answer are the same on every microscope:

| Key | What it is |
|---|---|
| `position_label` | the label you gave |
| `files` | every file the acquisition saved: the images, and anything beside them, such as the mock's command log |
| `planes` | for every image plane: its file, its channel, depth and moment (`c`, `z`, `t`, counted from 0), and where on the sample it was taken (`x_um`, `y_um`, `z_um`) |

Use the paths in `files` rather than building your own. Where the files go is
up to the driver. A position the driver cannot know is `None`.

A z-stack, saved in a folder of its own:

```python
answer = zmart_controller.acquire(
    position_label="cell 1",
    acquisition_settings={"z_planes": 3, "z_step_um": 2.0, "folder": "stacks"},
)
[(plane["z"], plane["z_um"]) for plane in answer["content"]["planes"]]
```
```
[(0, 0.0), (1, 2.0), (2, 4.0)]
```

On the mock, a stack starts at the current height and goes up. The files are
`stacks/cell_1_z000.ome.tif` to `cell_1_z002.ome.tif`. The space in the label
is made safe for a file name.

When the driver cannot confirm that the acquisition happened, the answer is
`success: False`, with no files and the reason in `content`.

## Procedures: get_procedures, run_procedure

Procedures are routines the microscope offers, such as autofocus. Each driver
offers its own.

```python
zmart_controller.get_procedures()["content"]
```
```
{'autofocus': {'description': 'Take a short z-stack around the current height,
   find the sharpest plane, and move there. Optional: range_um (default 20),
   step_um (default 2).'},
 'backlash_takeup': {'description': 'Approach the current position from the
   same side every time, so that positions repeat exactly.'},
 'zero_piezo': {'description': 'Move the piezo to the middle of its range,
   keeping the focus height.'}}
```

Run one by name. Anything else in the dictionary goes to the procedure as its
options, as its description says.

```python
answer = zmart_controller.run_procedure({"name": "autofocus", "range_um": 10, "step_um": 1})
answer["content"]["ran"]
```
```
'autofocus'
```

The answer always names the procedure under `ran`. The rest is the
procedure's own. An unknown name is refused with `ValueError`.

## When something goes wrong

Three kinds of outcome besides plain success, and each tells you where to
look.

| Outcome | Meaning | What to do |
|---|---|---|
| `ValueError` | Your request was wrong. Nothing was done | Fix the call. The matching `get_*` command shows what is allowed |
| `RuntimeError` | The microscope failed or refused | Look at the microscope and its software |
| `success: False` | A soft outcome: not what you asked, but safe to carry on | Read the reason in `content` |

Some examples:

```
ValueError: unknown acquisition setting 'fromat'
ValueError: set laser_power refused: laser_power = 90.0 is outside the limits [0.0, 50.0]
ValueError: unknown actuator 'laser' for axis 'z'
ValueError: unknown procedure 'nope'
RuntimeError: session is disconnected
```

Calling a command before any microscope is plugged in raises an
`AttributeError` that says so:

```
AttributeError: no active microscope - call set_instrument(...) before zmart_controller.get_xyz(...)
```

The controller passes every error from the driver to you unchanged.

## Several microscopes at once

The module-level style drives one microscope at a time. To drive several,
make a `ZmartController` for each. It has the same commands as the module,
and making one connects.

```python
from zmart_controller import ZmartController

left = ZmartController("mock", {"output_root": "left"})
right = ZmartController("mock", {"output_root": "right"})

left.set_xyz(0, 0, 0)
right.set_xyz(200, 0, 0)
left.acquire(position_label="A1")
right.acquire(position_label="A1")

left.disconnect()
right.disconnect()
```

Controllers made this way are independent of each other. Plugging in one never
disconnects another. This is also the way to drive microscopes from several
threads: one controller per thread.

## What works on every microscope

A workflow that should run on every microscope may rely on:

- the commands themselves, with the arguments shown on this page;
- the `{"success", "content"}` answer, and the errors described above;
- `output_root` and `description` in `get_info`;
- `value`, `actuator` and `canvas` per axis in `get_xyz`;
- `changeable` and `observed` in `get_state`;
- `options` and `active` per setting in `get_acquisition_settings`;
- `position_label`, `files` and `planes` in the answer of `acquire`;
- `ran` in the answer of `run_procedure`.

Everything else is an extra of a particular driver: the mock's `serial` and
`readback`, the names of its settings and procedures, its `folder` setting.
Extras are fine to use. A workflow that needs them runs only on microscopes
whose drivers offer them. Look settings and procedures up with `get_state`,
`get_acquisition_settings` and `get_procedures` rather than assuming them.
Then your workflow tells you clearly when a microscope lacks something.

## All commands at a glance

| Command | What it does | Key parts of the answer |
|---|---|---|
| `set_instrument(driver, connection=None)` | Plug in a driver and connect | returns the session |
| `disconnect()` | Close the connection | nothing |
| `get_info()` | Describe the setup | `output_root`, `description` |
| `get_actuators()` | The motors of each axis | `{axis: [motor names]}` |
| `get_xyz(with_actuators=None)` | Read the position | per axis: `value`, `actuator`, `canvas` |
| `set_xyz(x, y, z, with_actuators=None)` | Move, in µm from the origin | `position`, `actuators` |
| `get_state()` | Capture the settings | `changeable`, `observed` |
| `set_state(state)` | Apply the `changeable` settings | what was applied |
| `get_acquisition_settings()` | The choices for capturing and saving | per setting: `options`, `active` |
| `acquire(position_label, acquisition_settings=None)` | Capture and save here | `position_label`, `files`, `planes` |
| `get_procedures()` | The routines on offer | per routine: `description` |
| `run_procedure({"name": ..., ...})` | Run one routine | `ran` |

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
