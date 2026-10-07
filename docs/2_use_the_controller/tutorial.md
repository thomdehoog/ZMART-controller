# Use the controller, step by step

This is a walk-through for someone who would like to drive a microscope from
Python with the ZMART Controller, and has not used it before. It explains the
idea, takes you through a first session on the simulated microscope that comes
with the controller, and then shows a few small scripts you can adapt. The
[README](README.md) of this part is the complete documentation of every
command.

## The idea

Every microscope comes with its own software and its own way of being
programmed. The ZMART Controller puts one short list of plain commands in
front of all of them: move, read and apply the settings, take a picture, run a
routine such as autofocus. A *driver* translates these commands for one
particular microscope.

```
your Python  ──► zmart_controller  ──► driver  ──► microscope
```

The controller comes with one driver already: the **mock driver**, a
simulated microscope that runs entirely on your computer. It moves, takes
real pictures of a pretend slide with fluorescent spots, blurs when out of
focus, and refuses moves beyond its limits, just like a real one. Everything
in this tutorial runs on it, so you can follow along on a laptop. On a real
microscope, only the first step changes.

## Before you start

- Python 3.11 or newer.
- The controller, installed into that Python:

  ```
  pip install "git+https://github.com/thomdehoog/ZMART-controller"
  ```

- A way to look at images: [Fiji](https://fiji.sc) or
  [napari](https://napari.org). Both open the OME-TIFF files the mock saves.

Open Python by typing `python` in a terminal, or open a Jupyter notebook, and
type the lines below one at a time.

## Step 1: plug in a driver

```python
import zmart_controller

zmart_controller.set_instrument("mock")
```

`set_instrument` plugs in a driver and connects to its microscope. From now
on, every command you call on `zmart_controller` goes to this microscope. The
mock driver starts its pretend microscope software in the background; a real
driver would connect to the microscope's software instead.

## Step 2: meet the microscope

```python
info = zmart_controller.get_info()
print(info["content"]["description"])
```

Every command answers with the same two things: `success`, which says whether
the driver did what you asked, and `content`, which is what it has to say. The
`description` is the microscope in plain words. For the mock it begins:

```
A pretend widefield fluorescence microscope that runs entirely in software
(MockScope Control), for trying workflows without hardware. ...
```

and goes on to explain the stage, the objectives and every setting. Read it
whenever you meet a new microscope.

Two more facts are worth knowing early:

```python
print(info["content"]["output_root"])
```

is the folder where the images will be saved, and

```python
zmart_controller.get_acquisition_settings()["content"]
```

lists the choices you have when taking a picture. We use them in step 6.

## Step 3: where is the stage?

```python
position = zmart_controller.get_xyz()["content"]
print(position["x"])
```
```
{'value': 0.0, 'actuator': 'motoric', 'canvas': [-5032.0, 5032.0]}
```

Positions are in micrometres from the *origin*, a point (0, 0, 0) that was
chosen once for this microscope. `value` is where the axis is now, and
`canvas` is everywhere a picture can show: on the mock, the stage travels
5 mm to either side in x and y and 0.5 mm up or down in z, and a picture at
the edge shows another 32 µm beyond it in x and y.

## Step 4: move

```python
zmart_controller.set_xyz(100, 50, 0)
print(zmart_controller.get_xyz()["content"]["x"]["value"])
```
```
100.0
```

`set_xyz` always takes all three axes, in micrometres from the origin, so a
script always says exactly where it wants to be. It returns once the stage
has arrived.

Try a move that is too far:

```python
zmart_controller.set_xyz(99999, 0, 0)
```
```
ValueError: move refused: x would go to 149999.00 µm (stage coordinates), outside the travel range [45000.0, 55000.0] set in the limits
```

Nothing moved. The driver checks every move against the limits before
sending it. (The message counts in the stage's own coordinates, where the
limits are set, so its numbers differ from yours by the origin.)

One more thing to know about directions: **in a saved image, right is +x and
down is +y**, on every microscope. A picture taken at a larger x shows what
lay to the right.

## Step 5: look at the settings and change one

```python
state = zmart_controller.get_state()["content"]
print(state["changeable"])
```
```
{'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0, 'objective': 1}
```

The *state* has two parts. `changeable` holds the settings you can change;
`observed` describes the microscope as it is, such as the objective's name
and the pixel size, and is only for reading.

To change a setting, edit the state and apply it:

```python
state["changeable"]["laser_power"] = 20.0
zmart_controller.set_state(state)["content"]["applied"]["laser_power"]
```
```
20.0
```

You can also apply only the settings you name; the others stay as they are:

```python
zmart_controller.set_state({"changeable": {"exposure_ms": 20.0}})
```

Keep the captured state in a variable, and you can put the microscope back
into exactly these settings later with one `set_state`.

## Step 6: take a picture

```python
answer = zmart_controller.acquire(position_label="first")
print(answer["content"]["files"])
```
```
['/tmp/zmart-mock-output/first.ome.tif', '/tmp/zmart-mock-output/first.commands.json']
```

`acquire` captures an image with the current settings at the current
position, and saves it. `position_label` names the position in the saved
files. The answer lists under `files` every file it saved: here the image,
and a log of the commands the mock sent to make it. Your path will differ;
use the one printed on your screen.

Open the `.ome.tif` file in Fiji (*File > Open*) or napari (drag it onto the
window). You should see small bright spots, like fluorescent beads.

The answer also says where on the sample the picture was taken:

```python
answer["content"]["planes"]
```
```
[{'path': '/tmp/zmart-mock-output/first.ome.tif', 'c': 0, 'z': 0, 't': 0, 'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}]
```

Take the same label again and nothing is overwritten: the second picture is
saved as `first_001.ome.tif`.

## Step 7: a z-stack

A z-stack is a series of pictures at different heights. On the mock it is
chosen with two acquisition settings, `z_planes` and `z_step_um`; we also
put it in a folder of its own:

```python
answer = zmart_controller.acquire(
    position_label="stack",
    acquisition_settings={"z_planes": 5, "z_step_um": 2.0, "folder": "stacks"},
)
for plane in answer["content"]["planes"]:
    print(plane["z"], plane["z_um"], plane["path"])
```
```
0 0.0 /tmp/zmart-mock-output/stacks/stack_z000.ome.tif
1 2.0 /tmp/zmart-mock-output/stacks/stack_z001.ome.tif
2 4.0 /tmp/zmart-mock-output/stacks/stack_z002.ome.tif
3 6.0 /tmp/zmart-mock-output/stacks/stack_z003.ome.tif
4 8.0 /tmp/zmart-mock-output/stacks/stack_z004.ome.tif
```

The stack starts at the current height and goes up. Settings you leave out
keep their active value, so the next `acquire` without settings takes a
single plane again. Open the five files one after the other: the spots are
sharp in some planes and blurred in others.

## Step 8: run autofocus

The microscope offers a few routines of its own:

```python
for name, procedure in zmart_controller.get_procedures()["content"].items():
    print(name, "-", procedure["description"])
```
```
autofocus - Take a short z-stack around the current height, find the sharpest plane, and move there. Optional: range_um (default 20), step_um (default 2).
backlash_takeup - Approach the current position from the same side every time, so that positions repeat exactly.
zero_piezo - Move the piezo to the middle of its range, keeping the focus height.
```

Run autofocus and see where it put the focus:

```python
zmart_controller.run_procedure({"name": "autofocus"})
print(zmart_controller.get_xyz()["content"]["z"]["value"])
```

The pretend slide is slightly tilted, so the sharpest height depends a little
on where you are. Options go in the same dictionary as the name, for example
`{"name": "autofocus", "range_um": 10, "step_um": 1}`.

## Step 9: disconnect

```python
zmart_controller.disconnect()
```

This closes the connection. Any command now raises an error that tells you to
call `set_instrument` first.

## Step 10: when something goes wrong

Three kinds of error can come back, and each tells you where to look.

- **`ValueError`: the request was wrong.** A move beyond the limits, a setting
  outside its range, a misspelt acquisition setting such as `"fromat"`, an
  unknown procedure. Nothing was done. Fix the call; the matching `get_*`
  command shows what is allowed.
- **`RuntimeError`: the microscope failed or refused.** For example a move that
  could not be confirmed, or a command after `disconnect`. Look at the
  microscope.
- **`success: False`: it did not quite work, but it is safe to carry on.** For
  example a setting that was sent but never confirmed. The details are in
  `content`.

## Small scripts to adapt

A script is the session above, written in a file and run with
`python myscript.py`. Each script plugs in the mock; on a real microscope,
plug in its driver instead and keep the rest.

**A row of positions, one picture each.**

```python
import zmart_controller

zmart_controller.set_instrument("mock")

for i in range(5):
    zmart_controller.set_xyz(i * 200, 0, 0)  # 200 um apart
    zmart_controller.acquire(position_label=f"row_{i}")

zmart_controller.disconnect()
```

**A grid, saved in its own folder.**

```python
import zmart_controller

zmart_controller.set_instrument("mock")

step = 64  # one field of view of the 10x objective, so the pictures just touch
for row in range(3):
    for column in range(3):
        zmart_controller.set_xyz(column * step, row * step, 0)
        zmart_controller.acquire(
            position_label=f"r{row}_c{column}",
            acquisition_settings={"folder": "grid"},
        )

zmart_controller.disconnect()
```

Because right is +x and down is +y, the picture `r0_c1` lies directly to the
right of `r0_c0`, and `r1_c0` directly below it.

**Save the settings to a file, and apply them again another day.**

```python
import json

import zmart_controller

zmart_controller.set_instrument("mock")

# Today: capture the settings you are happy with.
state = zmart_controller.get_state()["content"]
with open("my_settings.json", "w") as file:
    json.dump(state, file, indent=2)

# Another day: put the microscope back into exactly these settings.
with open("my_settings.json") as file:
    zmart_controller.set_state(json.load(file))

zmart_controller.disconnect()
```

**A time series at one position.**

```python
import time

import zmart_controller

zmart_controller.set_instrument("mock")

for t in range(6):  # six pictures, 10 seconds apart
    zmart_controller.acquire(
        position_label=f"t{t:03d}",
        acquisition_settings={"folder": "timeseries"},
    )
    time.sleep(10)

zmart_controller.disconnect()
```

**Check the answer before carrying on.**

```python
import zmart_controller

zmart_controller.set_instrument("mock")

answer = zmart_controller.acquire(position_label="checked")
if answer["success"]:
    print("saved:", answer["content"]["files"])
else:
    print("not saved:", answer["content"])

zmart_controller.disconnect()
```

## Points to be aware of

- **Every command waits until it is done.** When `set_xyz` returns, the stage
  has arrived; when `acquire` returns, the files are saved.
- **Units.** Positions and steps in micrometres. Each driver's `description`
  gives the units of its settings, such as milliseconds for the mock's
  `exposure_ms`.
- **Use the paths from `files`.** Where and under which name a microscope
  saves its pictures is up to its driver. The paths in the answer are always
  right; paths you build yourself may not be on another microscope.
- **Names of settings and procedures belong to the microscope.** The mock's
  `laser_power`, `folder` or `autofocus` may be called differently, or not
  exist, on another microscope. Look them up with `get_state`,
  `get_acquisition_settings` and `get_procedures`.
- **Where the mock saves.** Unless you choose a folder, the mock saves in your
  computer's temporary folder, so trying things never fills up a project.
  Choose your own with
  `zmart_controller.set_instrument("mock", {"output_root": "my_images"})`.
- **A faster mock.** The mock takes a little time for every move and picture,
  like a real microscope. For quick tests, plug it in with
  `{"mock_timing": "instant"}`.
- **The configuration folder.** A real driver keeps what it measured once for
  its microscope, such as the origin, the travel limits and the calibration,
  in a folder on that computer: `C:\ProgramData\zmart-microscopy\` on Windows,
  `/Library/Application Support/zmart-microscopy/` on macOS and
  `/etc/zmart-microscopy/` on Linux, or the folder named by the
  `ZMART_MICROSCOPY_ROOT` environment variable. You never edit it by hand; the
  driver's own setup step writes it.

## Where to go next

- The [README](README.md) of this part: every command, every answer, and what
  a workflow may rely on on every microscope.
- Part 1, [plug in a driver](../1_plug_in_a_driver/README.md): how drivers
  work, and how to write one for your own microscope.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
