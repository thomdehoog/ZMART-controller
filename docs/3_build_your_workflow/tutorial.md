# Build your workflow, step by step

This is a walk-through for someone who would like to automate an experiment
and has never written a microscope workflow before. Together we build a small
but real smart-microscopy workflow on the mock microscope: an overview scan
that finds bright spots, followed by a detailed scan of each spot. At the end,
we move it to a real microscope. The [README](README.md) is the complete
documentation of this part.

## The idea

Imagine a slide with a few fluorescent cells scattered across it. Imaging the
whole slide at high magnification would take a long time and bleach every
cell. A smart workflow does it in two rounds instead:

1. **An overview** at low magnification, quick and gentle, covering the area.
2. **A look at the pictures**, by your own analysis, to find where the cells
   are.
3. **A detailed scan** at high magnification, as a z-stack, of only the
   places the analysis found.

The mock microscope shows a slide of small bright spots, like fluorescent
beads, so it is a good place to build exactly this. The workflow only uses the
controller's commands, so once it works on the mock, it works on any
microscope with a driver.

## Before you start

- Python 3.11 or newer, with the controller installed:

  ```
  pip install "git+https://github.com/thomdehoog/ZMART-controller"
  ```

- Two packages for the analysis: [tifffile](https://pypi.org/project/tifffile/)
  reads the saved pictures, and [numpy](https://numpy.org) does the arithmetic
  on them. The controller itself does not need them; your workflow does.

  ```
  pip install tifffile numpy
  ```

- A Python session to type into: `python` in a command window, or a Jupyter
  notebook. Enter the blocks below in order, in the same session, since each
  step uses what the step before it made.

## Step 1: set the mock up, once

A real microscope is set up once before anyone runs a workflow on it: its
driver measures where (0, 0, 0) is, how the camera sits on the stage, and how
far each objective's view is shifted. The mock is delivered like a microscope
nobody has set up yet. Its pictures are fine, but its camera is mounted turned
and mirrored, and its objectives do not line up exactly, so turning a pixel
into a stage position would come out wrong.

On a real microscope you would run the driver's setup step. The mock can
simply tell us the right answers, which a real microscope never can, so we
save those.

Drivers keep their setup in a folder shared by everyone on the computer
(`C:\ProgramData\zmart-microscopy` on Windows). On a Mac or on Linux that
folder needs administrator rights to write, so for the mock we point the
controller at a folder of our own, `zmart-config`, through the
`ZMART_MICROSCOPY_ROOT` setting:

```python
import os

os.environ["ZMART_MICROSCOPY_ROOT"] = "zmart-config"

import zmart_controller
from zmart_controller.mock.configuration import save

session = zmart_controller.set_instrument(zmart_controller.mock)
truth = session._handle.scope.truth()   # only the mock knows its own truth
zmart_controller.disconnect()

save(
    "image_stage_registration",
    {
        "orientation": [list(row) for row in truth["orientation"]],
        "pixel_size_um": {"1": 1.0, "2": 0.5, "3": 0.25},
    },
)
save("optical_calibration", {"objective_offsets_um": truth["objective_offsets_um"]})
```

The mock saves these in that configuration folder, just as a real driver
keeps its own setup, and reads them every time it connects. You do this once.
In a new Python session, set `ZMART_MICROSCOPY_ROOT` to the same folder again
before plugging in the mock, and it is still set up.

## Step 2: plug in the driver, and plan

Plug the mock in, and tell it to keep the pictures in a folder called
`zmart-tutorial` next to where you started Python:

```python
import zmart_controller

zmart_controller.set_instrument(zmart_controller.mock, {"output_root": "zmart-tutorial"})
```

Now the plan. Everything that belongs to this particular microscope goes at
the top, in one place: the names of its settings and the values we want. When
we move to another microscope, these are the lines to check.

```python
# The settings of each round, in this microscope's own names.
# Check them with zmart_controller.get_state() on another microscope.
OVERVIEW = {"objective": 1, "laser_power": 10.0}   # 10x: a wide, gentle view
DETAIL = {"objective": 3, "laser_power": 10.0}     # 40x: a close look
STACK = {"z_planes": 5, "z_step_um": 2.0}          # 5 planes, 2 um apart

# The overview: a grid of 3 x 3 tiles. At 10x a picture covers 64 um,
# so tiles 64 um apart sit edge to edge.
TILE_UM = 64
GRID = [(col * TILE_UM, row * TILE_UM) for row in range(3) for col in range(3)]
```

The grid is 9 positions, in micrometres from the origin. Have a look at how
far the stage can travel, so you know the plan fits:

```python
zmart_controller.get_xyz()["content"]["x"]["range"]
```

`[-5000.0, 5000.0]`: our grid, from 0 to 128 um, is well inside.

## Step 3: the overview

Apply the overview settings, visit each tile, and take a picture. The
`folder` setting keeps this round's files together in a folder of their own:

```python
zmart_controller.set_state({"changeable": OVERVIEW})

overview = []
for i, (x, y) in enumerate(GRID):
    zmart_controller.set_xyz(x, y, 0)
    answer = zmart_controller.acquire(
        position_label=f"tile_{i:02d}",
        acquisition_settings={"folder": "overview"},
    )
    if not answer["success"]:
        raise RuntimeError(f"tile {i} was not taken: {answer['content']}")
    overview += answer["content"]["planes"]

len(overview)
```

`9`: one entry per picture. Look at one of them:

```python
overview[4]
```

```
{'path': 'zmart-tutorial/overview/tile_04.ome.tif', 'c': 0, 'z': 0, 't': 0,
 'x_um': 64.0, 'y_um': 64.0, 'z_um': 0.0}
```

This is what makes the next step possible. Each entry says which file the
picture is in and where the stage stood when it was taken. Open a file in
Fiji or napari if you like: small bright spots on a dark background.

## Step 4: find the spots

Now our own analysis. For each picture, we take its brightest pixel. If it is
much brighter than the background, there is a spot there, and we turn that
pixel into a stage position.

Two facts make the conversion work on any microscope. The stage position in
`planes` is the centre of the picture. And in every saved picture, right is
+x and down is +y. So we start at the centre, and step by the pixel size,
which the file itself stores:

```python
import numpy as np
import tifffile


def pixel_size_um(path):
    """The size of one pixel in micrometres, as the OME-TIFF file stores it."""
    with tifffile.TiffFile(path) as tif:
        pixels = tifffile.xml2dict(tif.ome_metadata)["OME"]["Image"]["Pixels"]
    return pixels["PhysicalSizeX"], pixels["PhysicalSizeY"]


def find_spot(plane):
    """The stage position of the brightest spot in this picture, or None if it has none."""
    image = tifffile.imread(plane["path"]).astype(float)
    row, column = np.unravel_index(np.argmax(image), image.shape)
    if image[row, column] < 5 * np.median(image):   # not clearly above the background
        return None
    size_x, size_y = pixel_size_um(plane["path"])
    height, width = image.shape
    x = plane["x_um"] + (column - (width - 1) / 2) * size_x
    y = plane["y_um"] + (row - (height - 1) / 2) * size_y
    return float(x), float(y)


targets = [spot for spot in map(find_spot, overview) if spot is not None]
[(round(x, 1), round(y, 1)) for x, y in targets]
```

Each pair is a spot, in micrometres on the stage. The analysis is a function
of its own, so you can later swap in anything you like, for example a cell
segmentation, as long as it returns positions in micrometres.

## Step 5: the detailed scan

Switch to the detailed settings and visit each spot. Each acquisition is a
z-stack. The mock's stack starts at the height the stage is at and goes up,
so we start 4 um below the focus, and the 5 planes, 2 um apart, are centred on
it. From the stack we pick the plane in which the spot is brightest, which is
where it is in focus:

```python
zmart_controller.set_state({"changeable": DETAIL})

for i, (x, y) in enumerate(targets):
    zmart_controller.set_xyz(x, y, -4)
    answer = zmart_controller.acquire(
        position_label=f"spot_{i:02d}",
        acquisition_settings={"folder": "detail", **STACK},
    )
    if not answer["success"]:
        print(f"spot {i}: not taken, {answer['content'].get('reason')}")
        continue
    planes = answer["content"]["planes"]
    brightness = [tifffile.imread(p["path"]).max() for p in planes]
    best = planes[int(np.argmax(brightness))]
    print(f"spot {i}: sharpest at z = {best['z_um']:.1f} um, in {best['path']}")
```

Open a few of the detailed pictures: each spot sits in the middle of its
picture, now four times larger. That is the proof that the whole chain works:
the overview found the spot, the conversion put it at the right place on the
stage, and the detailed scan went there.

Finally, close the connection:

```python
zmart_controller.disconnect()
```

All pictures are in `zmart-tutorial/overview/` and `zmart-tutorial/detail/`,
each with a `.commands.json` beside it that records what the microscope was
asked to do and how it answered.

## Step 6: move it to a real microscope

Write the steps above into one file, `my_workflow.py`, without step 1, which
only the mock needs. To run it on a real microscope:

1. **Install the microscope's driver and set it up**, as its README says. The
   setup step does for the real microscope what step 1 did for the mock.
2. **Plug in that driver.** Only this line changes:

   ```python
   from zmart_drivers.leica import stellaris   # the driver of your microscope

   zmart_controller.set_instrument(stellaris)
   ```

3. **Check the names at the top.** Ask the microscope for its own:

   ```python
   zmart_controller.get_state()["content"]["changeable"]   # e.g. objective, laser power
   zmart_controller.get_acquisition_settings()["content"]  # e.g. z_planes, folder
   ```

   Edit `OVERVIEW`, `DETAIL` and `STACK` to match, and the tile spacing to the
   field of view of its objective.
4. **Start small.** Run a 1 x 1 grid on a sample you can replace, and keep an
   eye on the microscope during the first round.

The rest of the workflow, the loops, the analysis and the conversion from
pixels to micrometres, stays exactly as it is. That is the point of writing
it against the controller.

## Points to be aware of

- **Errors stop the run, on purpose.** A position outside the limits, or a
  move that could not be confirmed, raises an error rather than carrying on.
  Do not hide these behind a `try` that ignores them.
- **`success: False` is yours to handle.** It means the driver could not
  confirm an acquisition or a setting, but carrying on is safe. Above, the
  overview stops and the detailed scan skips the spot; choose what suits your
  experiment.
- **The brightest pixel is a simple analysis.** It finds one spot per tile
  and will miss a second one. It is there to show the shape of the workflow;
  replace `find_spot` with a real detection for your own samples.
- **Do not rely on extras.** Our workflow reads only `files`, `planes` and
  the pixel size stored in the file, which every driver provides. Keys a
  particular driver adds are fine to look at, but not to depend on.

## Where to go next

- The [README](README.md) of this part: the rules that keep a workflow
  portable, the file layout, and reading the saved pictures.
- The [example notebook](example_workflow.ipynb): another small workflow,
  ready to copy.
- Part 2, [Drive the microscope](../2_drive_the_microscope/README.md): every
  command and what it answers.
- Part 1, [Plug in a driver](../1_plug_in_a_driver/README.md): how to write
  a driver for a microscope that does not have one yet.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
