# 2. Use the controller

Every command of the ZMART Controller, from the side of the person who drives
the microscope.

This page is the documentation of the controller's commands. For a
step-by-step walk-through, see the [tutorial](tutorial.md).

Every example below runs on the mock driver, the simulated microscope that
comes with the controller, and the outputs are real answers from it, trimmed
where they are long. On another microscope the numbers differ, but the shape
of every answer is the same.

## Contents

1. [The idea](#the-idea)
2. [Plug in and disconnect](#plug-in-and-disconnect)
3. [Every answer has the same shape](#every-answer-has-the-same-shape)
4. [Learn about the setup: get_info](#learn-about-the-setup-get_info)
5. [Position: get_actuators, get_xyz, set_xyz](#position-get_actuators-get_xyz-set_xyz)
6. [Settings: get_state, set_state](#settings-get_state-set_state)
7. [Acquire: get_acquisition_settings, acquire](#acquire-get_acquisition_settings-acquire)
8. [Procedures: get_procedures, run_procedure](#procedures-get_procedures-run_procedure)
9. [When something goes wrong](#when-something-goes-wrong)
10. [Several microscopes at once](#several-microscopes-at-once)
11. [What a workflow may rely on](#what-a-workflow-may-rely-on)
12. [All commands at a glance](#all-commands-at-a-glance)

## The idea

The controller offers a short, fixed list of commands: plug in a microscope,
learn about it, move, read and apply settings, acquire, run a routine such as
autofocus, and disconnect. You send the commands; the driver of the connected
microscope carries them out and answers.

```
your script  ──► zmart_controller  ──► driver  ──► microscope
             ◄── {"success", "content"} ◄──
```

The controller itself does no microscope work. It hands each command to the
driver and gives you the driver's answer unchanged. Every check, such as
whether a position is inside the travel limits, happens in the driver, because
only the driver knows the hardware.

Every command is *synchronous*: it returns only when the driver has finished,
so the next line of your script always starts from a microscope that is done
with the previous one.

## Plug in and disconnect

```python
import zmart_controller

zmart_controller.get_drivers()
```
```
['mock']
```

`get_drivers()` lists the drivers registered on this computer, by name. The
mock driver, a simulated microscope, is always there; part 1 explains how to
register the driver of a real microscope, once, with `register_driver`.

```python
zmart_controller.set_instrument("mock")
```

`set_instrument(driver, connection=None)` plugs in a driver, connects to its
microscope, and makes it the *active* microscope: every command you call on
the module afterwards, such as `zmart_controller.set_xyz(...)`, goes to it.

- `driver` is a name from `get_drivers()`. It can also be the driver module
  itself, such as `zmart_controller.mock`, which is handy while you write a
  driver.
- `connection` is an optional dictionary that is handed to the driver
  unchanged. It holds whatever that driver needs to connect, such as the name
  of the computer the microscope software runs on. Each driver's README lists
  what it accepts. The mock accepts `output_root` (the folder for its images),
  `mock_timing` (`"realistic"`, the default, or `"instant"`) and `token` (its
  pretend login):

  ```python
  zmart_controller.set_instrument("mock", {"output_root": "my_images"})
  ```

  A driver's own configuration, the `CONNECTION` in its
  `zmart_controller_plugin.py`, is used when you leave this out, so you
  usually do.

If the driver is missing one of the functions the controller needs,
`set_instrument` refuses it at once with a `ValueError` naming the missing
functions, before anything connects.

Plugging in a second microscope disconnects the first. To close the
connection yourself:

```python
zmart_controller.disconnect()
```

Afterwards every command raises an error until `set_instrument` is called
again. Calling `disconnect` twice is harmless.

Two cautions for this short, module-level style:

- **Call through the module each time**, as in `zmart_controller.set_xyz(...)`.
  A command saved in a variable, such as `move = zmart_controller.set_xyz`,
  keeps pointing at the old microscope after you plug in another one.
- **It assumes one thread.** If several threads drive microscopes at the same
  time, give each its own session (see
  [Several microscopes at once](#several-microscopes-at-once)).

`set_instrument` also returns the session it made, in case you want to hold on
to it. Its one attribute, `context`, names the driver:

```python
session = zmart_controller.set_instrument("mock")
session.context
```
```
{'driver': 'mock'}
```

## Every answer has the same shape

Every command except `disconnect` answers with a dictionary of two things:

```python
{"success": True, "content": {...}}
```

- `success` says whether the driver did what you asked.
- `content` is what the driver has to say about it: a position, a list of
  saved files, a state.

`success: False` means the outcome is safe to carry on from, but not what you
asked for; the reason is in `content`. Anything that is not safe to carry on
from is raised as an error instead (see
[When something goes wrong](#when-something-goes-wrong)). We have not yet
defined a common vocabulary for the reasons themselves.

## Learn about the setup: get_info

```python
zmart_controller.get_info()["content"]
```
```
{'output_root': '/tmp/zmart-mock-output',
 'description': 'A pretend widefield fluorescence microscope that runs entirely
   in software (MockScope Control), for trying workflows without hardware. ...
   Objectives, by slot: 1 is 10x/0.30 Air (1.0 um per pixel), 2 is 20x/0.75 Air
   (0.5 um per pixel), 3 is 40x/0.95 Air (0.25 um per pixel). ...',
 'serial': 'MOCK-0001',
 'software': {'software': 'MockScope Control', 'version': '2.4.1'},
 ...}
```

Two keys are the same on every microscope:

- `output_root` is the folder where the driver saves images.
- `description`, when the driver gives one, is the microscope in plain words:
  what each setting means, its unit and its bounds, which objective sits in
  which slot. It is written for whoever drives the microscope: you, or the
  ZMART AI agent, which learns the instrument from it. Read it once when you
  meet a new microscope.

Everything else in `get_info`, such as the mock's `serial`, is an extra of
that driver.

## Position: get_actuators, get_xyz, set_xyz

### The coordinates

Positions are in **micrometres from the origin**, a point (0, 0, 0) that was
chosen and saved once for this microscope when its driver was set up. They are
not the raw numbers of the stage, so a position means the same place on the
sample every time you connect.

The positions and the pictures share one frame, the one in which you observe
the specimen: **in a saved image, right is +x and down is +y**. A picture
taken further along +x shows the part of the specimen that lay to its right.
The driver arranges this, whatever way the camera or the stage is mounted, so
"left", "right", "up" and "down" mean the same on every microscope. Which way
+z points, towards the objective or away from it, is the microscope's own; the
driver says so in its `description`.

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

- `value` is where the axis is now.
- `actuator` is the motor that was read (see below).
- `canvas` is everywhere a picture can show on that axis, as `[min, max]`. A
  picture taken at the edge of the stage's travel still shows half a field
  beyond it, so the canvas is the travel widened by half the largest field of view (here 64 µm wide, so 32 µm
  on each side). For z, it is widened by half the deepest stack the driver
  takes, unless the limits already keep every stack inside the travel, as on
  the mock. The interface and the viewer use `canvas` to lay out the whole
  specimen area before the first picture arrives. Plan your positions half a
  field inside it: the stage itself stops at the travel limits, and a move
  beyond them is refused.

### get_actuators and with_actuators

Some axes have more than one motor. On the mock, z has a coarse `"motoric"`
drive for long moves and a `"piezo"` for fine, fast steps:

```python
zmart_controller.get_actuators()["content"]
```
```
{'x': ['motoric'], 'y': ['motoric'], 'z': ['motoric', 'piezo']}
```

Name the motor you want per axis with `with_actuators`, on both `get_xyz` and
`set_xyz`. Axes you leave out use the driver's default, the first in the list.

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
used; the mock adds `readback`, the position it read back after the move.

A move that the driver cannot confirm raises `RuntimeError`, because carrying
on at an unknown position is never safe. A move outside the travel range is
refused with `ValueError` before anything moves:

```python
zmart_controller.set_xyz(99999, 0, 0)
```
```
ValueError: move refused: x would go to 149999.00 µm (stage coordinates),
outside the travel range [45000.0, 55000.0] set in the limits
```

The message speaks in the stage's own coordinates, because that is where the
limits are set; the numbers differ from yours by the origin.

## Settings: get_state, set_state

A *state* is a snapshot of the microscope's settings: everything that decides
what an image looks like, such as the objective, laser power and exposure.

```python
zmart_controller.get_state()["content"]
```
```
{'changeable': {'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0,
                'objective': 1},
 'observed': {'serial': 'MOCK-0001', 'objective': '10x/0.30 Air',
              'pixel_size': {'x': 1.0, 'y': 1.0, 'unit': 'um'},
              'frame_size': {'x': 64.0, 'y': 64.0, 'unit': 'um'},
              'software': {'software': 'MockScope Control', 'version': '2.4.1'}}}
```

It has two parts:

- `changeable` holds the settings that `set_state` can apply. Which settings
  there are, and what they mean, is the microscope's own; the `description`
  from `get_info` explains them.
- `observed` describes the microscope as it is, such as the objective's name
  and the pixel size. It is for reading only: `set_state` never acts on it.

The usual way to use states is to capture one, change what you need, and
apply it later, as often as you like:

```python
overview = zmart_controller.get_state()["content"]
overview["changeable"]["laser_power"] = 20.0

zmart_controller.set_state(overview)["content"]
```
```
{'applied': {'objective': 1, 'laser_power': 20.0, 'gain': 100.0,
             'exposure_ms': 10.0},
 'unconfirmed': {}, 'ignored': []}
```

You can also apply only a few settings; the rest stay as they are:

```python
zmart_controller.set_state({"changeable": {"gain": 200.0}})["content"]
```
```
{'applied': {'gain': 200.0}, 'unconfirmed': {}, 'ignored': []}
```

A value outside the microscope's limits is refused with `ValueError`. When a
setting was sent but the microscope never showed it, the answer is
`success: False`, and the mock lists that setting under `unconfirmed` with the
reason. A state is a plain dictionary, so you can save it to a file with
`json` and apply it again on another day.

## Acquire: get_acquisition_settings, acquire

### get_acquisition_settings

The acquisition settings are the choices about *how* to capture and save, as
opposed to the microscope's settings in the state. Each driver offers its own.
For each one, `options` says what values it may take and `active` which value
is used when you say nothing:

```python
zmart_controller.get_acquisition_settings()["content"]
```
```
{'folder': {'options': 'any text; empty saves straight into output_root',
            'active': ''},
 'backlash_correction': {'options': [True, False], 'active': True},
 'format': {'options': ['ome-tiff', 'ome-zarr'], 'active': 'ome-tiff'},
 'z_planes': {'options': 'whole number from 1 up to the limit', 'active': 1},
 'z_step_um': {'options': 'number > 0', 'active': 1.0}}
```

On the mock:

- `folder` puts the files in a folder of that name under `output_root`, for
  example to keep an overview and a detailed scan apart.
- `backlash_correction` approaches every position from the same side before
  capturing, so positions repeat exactly.
- `format` is the file format: OME-TIFF (one file per plane) or OME-Zarr (one
  folder for the whole acquisition).
- `z_planes` and `z_step_um` make a z-stack: that many planes, that far apart
  in micrometres.

When `options` cannot be listed, it is a short description such as
`"number > 0"`.

### acquire

```python
answer = zmart_controller.acquire(position_label="A1")
answer["content"]
```
```
{'position_label': 'A1', 'folder': '', 'format': 'ome-tiff',
 'settle': 'backlash-corrected', 'position': {'x': 100.0, 'y': 50.0, 'z': 0.0},
 'confirmed': True,
 'files': ['/tmp/zmart-mock-output/A1.ome.tif',
           '/tmp/zmart-mock-output/A1.commands.json'],
 'planes': [{'path': '/tmp/zmart-mock-output/A1.ome.tif',
             'c': 0, 'z': 0, 't': 0,
             'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}],
 'command_log': '/tmp/zmart-mock-output/A1.commands.json', ...}
```

`acquire(position_label, acquisition_settings=None)` captures an image with
the current settings at the current position, and saves it, in one step.

- `position_label` names this position in the saved files, such as `"A1"` or
  `"cell 3"`. It is required. A second acquisition with the same label never
  overwrites the first: the mock saves it as `A1_001`, then `A1_002`, and so
  on.
- `acquisition_settings` holds choices from `get_acquisition_settings`. Any
  you leave out keep their active value, and an unknown name is refused with
  `ValueError`, so a typo never passes silently.

Two keys of the answer are the same on every microscope, and they are how a
workflow finds its pictures:

- `files` lists every file the acquisition saved: the images, and anything
  saved beside them, such as the mock's command log. A format kept as a
  folder, such as OME-Zarr, is listed by its folder. Use these paths rather
  than building your own: where and under which name the files go is up to
  the driver.
- `planes` says, for every image plane, which file it is in, which channel,
  depth and moment it is (`c`, `z` and `t`, each counted from 0), and where on
  the sample it was taken (`x_um`, `y_um`, `z_um`, in the same micrometres as
  `get_xyz`). A position the driver cannot know is `None`.

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

On the mock, a stack starts at the current height and goes up in steps of
`z_step_um`; the files are `stacks/cell_1_z000.ome.tif` to `cell_1_z002`,
with the space in the label made safe for a file name.

When the driver cannot confirm that the acquisition happened, the answer is
`success: False`, with no files and the reason in `content`.

## Procedures: get_procedures, run_procedure

Procedures are routines the microscope offers, built from moves, settings
and images, such as autofocus. Each driver offers its own:

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

Run one by name; anything else in the dictionary goes to the procedure as
its options, as its description says:

```python
answer = zmart_controller.run_procedure({"name": "autofocus", "range_um": 10, "step_um": 1})
answer["content"]["ran"]
```
```
'autofocus'
```

The answer always names the procedure under `ran`; the rest is the
procedure's own (the mock's autofocus adds the sharpness score of every plane
it tried). An unknown name is refused with `ValueError`.

## When something goes wrong

There are three kinds of outcome besides plain success, and each tells you
where to look.

- **`ValueError`: your request was wrong.** A position outside the travel
  range, a setting outside its limits, an unknown acquisition setting,
  procedure or motor. Nothing was done. Fix the call; the matching `get_*`
  command shows what is allowed.

  ```
  ValueError: unknown acquisition setting 'fromat'
  ValueError: set laser_power refused: laser_power = 90.0 is outside the limits [0.0, 50.0]
  ValueError: unknown actuator 'laser' for axis 'z'
  ValueError: unknown procedure 'nope'
  ```

- **`RuntimeError`: the microscope failed or refused.** For example a move
  that could not be confirmed, or a command sent after the session was
  disconnected. Look at the microscope and its software.

  ```
  RuntimeError: session is disconnected
  ```

- **`success: False`: a soft outcome.** The driver did not manage what you
  asked, but it is safe to carry on, for example a setting that was sent but
  never confirmed. The details are in `content`. Check `success` wherever it
  matters to your experiment.

Calling a command before any microscope is plugged in raises an
`AttributeError` that says so:

```
AttributeError: no active microscope - call set_instrument(...) before zmart_controller.get_xyz(...)
```

The controller passes every error from the driver to you unchanged.

## Several microscopes at once

The module-level style drives one microscope at a time. To drive several, hold
a session for each. A session has the same commands as the module:

```python
from zmart_controller.session import set_instrument

left = set_instrument("mock", {"output_root": "left"})
right = set_instrument("mock", {"output_root": "right"})

left.set_xyz(0, 0, 0)
right.set_xyz(200, 0, 0)
left.acquire(position_label="A1")
right.acquire(position_label="A1")

left.disconnect()
right.disconnect()
```

Sessions made this way are independent of each other and of the active
microscope, so plugging in one never disconnects another. This is also the way
to drive microscopes from several threads: one session per thread.

## What a workflow may rely on

A workflow that should run on every microscope may rely on what every driver
must give:

- the commands themselves, with the arguments shown on this page;
- the `{"success", "content"}` answer, and the errors described above;
- `output_root` (and `description`, if the driver has one) in `get_info`;
- `value`, `actuator` and `canvas` per axis in `get_xyz`;
- `changeable` and `observed` in `get_state`;
- `options` and `active` per setting in `get_acquisition_settings`;
- `position_label`, `files` and `planes` in the answer of `acquire`;
- `ran` in the answer of `run_procedure`.

Everything else is an extra of a particular driver: the mock's `serial` and
`readback`, the names of its settings and procedures, its `folder`
acquisition setting. Extras are fine to use, but a workflow that needs them
runs only on microscopes whose drivers offer them. Look settings and
procedures up with `get_state`, `get_acquisition_settings` and
`get_procedures` rather than assuming them, and your workflow will tell you
clearly when a microscope lacks something.

## All commands at a glance

| Command | What it does | Key parts of the answer |
|---|---|---|
| `set_instrument(driver, connection=None)` | Plug in a driver and connect; it becomes the active microscope | returns the session |
| `disconnect()` | Close the connection | nothing |
| `get_info()` | Describe the setup | `output_root`, `description` |
| `get_actuators()` | The motors of each axis | `{axis: [motor names]}` |
| `get_xyz(with_actuators=None)` | Read the position and travel | per axis: `value`, `actuator`, `canvas` |
| `set_xyz(x, y, z, with_actuators=None)` | Move, in µm from the origin | `position`, `actuators` |
| `get_state()` | Capture the settings | `changeable`, `observed` |
| `set_state(state)` | Apply the `changeable` settings | what was applied |
| `get_acquisition_settings()` | The choices for capturing and saving | per setting: `options`, `active` |
| `acquire(position_label, acquisition_settings=None)` | Capture and save here | `position_label`, `files`, `planes` |
| `get_procedures()` | The routines on offer | per routine: `description` |
| `run_procedure({"name": ..., ...})` | Run one routine | `ran` |
