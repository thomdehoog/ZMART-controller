# Build your workflow

Put the controller's commands together into an automated workflow that runs on
any microscope with a driver.

This is part 3 of three; see the [overview](../../README.md). It builds on
part 1, [plugging in a driver](../1_plug_in_a_driver/README.md), and part 2,
[driving the microscope](../2_drive_the_microscope/README.md). The
[tutorial](tutorial.md) is a longer walk-through that builds a small smart
workflow on the mock microscope, from an overview scan to a detailed scan of
the spots it found. [`example_workflow.ipynb`](example_workflow.ipynb) is a
short notebook to start from. This page is the complete documentation of
part 3.

## Contents

1. [The idea](#the-idea)
2. [The shape of a smart-microscopy workflow](#the-shape-of-a-smart-microscopy-workflow)
3. [Build it at your desk, on the mock](#build-it-at-your-desk-on-the-mock)
4. [Move it to a real microscope](#move-it-to-a-real-microscope)
5. [Rules that keep a workflow portable](#rules-that-keep-a-workflow-portable)
6. [Where the files go](#where-the-files-go)
7. [Reading the saved images](#reading-the-saved-images)
8. [When something goes wrong](#when-something-goes-wrong)
9. [Good to know](#good-to-know)

## The idea

An automated workflow is a Python script or a notebook that runs an
experiment for you: where to go, with which settings, what to take, and what
to do with what it sees. Here, a workflow talks only to the controller. It
never calls the microscope's own software directly.

That one restriction is what gives you the two things the controller
promises:

- **You can build it without the microscope.** The controller does not care
  which driver is plugged in. While you write and test the workflow, you plug
  in the mock driver, a simulated microscope that comes with the controller,
  and run the whole experiment at your desk.
- **It runs on any microscope with a driver.** When the workflow is ready, you
  plug in the real microscope's driver instead. Nothing else changes, so the
  same workflow can be shared, reviewed and run on another microscope.

```
your workflow  ──►  zmart_controller  ──►  driver  ──►  microscope
(this part)         (the commands)         mock, Leica, Nikon, ...
```

## The shape of a smart-microscopy workflow

A *smart* workflow decides what to image next from what it has already seen.
Most of them follow the same loop:

1. **Plan.** Choose the settings and the positions: for example a grid of
   tiles that covers the sample.
2. **Acquire.** Visit each position and take a picture with `acquire`.
3. **Analyse.** Open the saved pictures and look for what interests you:
   cells, spots, a structure with a certain shape.
4. **Decide.** Turn what you found into new positions, in micrometres on the
   stage, and choose the settings for the next round.
5. **Acquire again.** Visit the new positions with the detailed settings,
   for example a higher magnification and a z-stack.

A classic example is an overview scan at low magnification, followed by a
detailed scan of only the cells that were found in it. That saves time and
light, because the detailed, slow imaging happens only where it matters.

The controller covers steps 2 and 5, and gives you everything step 4 needs:
each saved picture comes with the stage position it was taken at. Step 3 is
your own analysis, in any Python package you like.

In code, a workflow is mostly the commands of part 2 inside a loop:

```python
import zmart_controller

zmart_controller.set_instrument(zmart_controller.mock)

zmart_controller.set_state({"changeable": {"objective": 1}})
overview = []
for i, (x, y) in enumerate([(0, 0), (64, 0), (0, 64), (64, 64)]):
    zmart_controller.set_xyz(x, y, 0)
    answer = zmart_controller.acquire(position_label=f"tile_{i:02d}")
    overview += answer["content"]["planes"]

# ... your analysis turns the overview pictures into targets ...

zmart_controller.disconnect()
```

## Build it at your desk, on the mock

The mock driver behaves like a real microscope: it takes time to move,
refuses positions outside its limits, writes real OME-TIFF files, and shows a
slide of small bright spots that move with the stage and blur when the focus
is off. Plug it in with one line:

```python
zmart_controller.set_instrument(zmart_controller.mock)
```

A few things make building on the mock easier:

- **Where the pictures go.** By default the mock saves into a folder in your
  computer's temporary space. Pass a folder of your own to keep them:
  `set_instrument(zmart_controller.mock, {"output_root": "my-run"})`.
- **Speed.** Moves and acquisitions take a little time, as on a real
  microscope. To go through a long workflow quickly, pass
  `{"mock_timing": "instant"}`.
- **Setting the mock up.** Out of the box, the mock behaves like a microscope
  that nobody has calibrated yet: its camera is mounted turned and mirrored,
  and its objectives do not line up exactly. The pictures are fine, but
  turning a pixel into a stage position comes out wrong until the microscope
  is set up. On a real microscope, the driver's setup step measures this once.
  The mock can simply tell you the right answers; the
  [tutorial](tutorial.md#step-1-set-the-mock-up-once) shows the few lines that
  save them. The setup is saved in the computer's configuration folder, which
  on a Mac or on Linux needs administrator rights to write; the tutorial shows
  how to use a folder of your own instead.

The [example notebook](example_workflow.ipynb) is a complete small workflow
on the mock, ready to copy.

## Move it to a real microscope

When the workflow runs on the mock, move it to a real microscope:

1. **Install the microscope's driver** on the microscope computer, and run its
   setup step once, as its README describes. This is where the origin, the
   travel limits and the calibration are measured and saved.
2. **Plug in that driver instead of the mock.** This is the one line that
   changes:

   ```python
   from zmart_drivers.leica import stellaris   # the driver of your microscope

   zmart_controller.set_instrument(stellaris)
   ```

3. **Adjust the microscope's own names**, if your workflow uses any (see the
   next section): its settings in `get_state`, and its acquisition settings
   and procedures.
4. **Check the plan against this microscope.** `get_xyz()` shows how far each
   axis can travel here. Run the first round on a sample you can replace,
   and keep an eye on the microscope.

## Rules that keep a workflow portable

A workflow runs on any microscope only if it relies on nothing but the shared
vocabulary. These rules keep it that way.

- **Positions are micrometres from the origin.** `set_xyz` and `get_xyz` use
  the same frame on every microscope, with the origin set by the driver's
  setup. In a saved picture, right is +x and down is +y. Stay inside the
  `range` that `get_xyz` reports for each axis.
- **Find the pictures through `files` and `planes`.** Never build a path
  yourself: the content of `acquire` lists every saved file, and `planes`
  says which file holds which picture and where on the sample it was taken.
  That is the same on every microscope.
- **Keep the microscope's own names in one place.** The names of settings
  (`laser_power`, `objective`, ...), of acquisition settings (`z_planes`,
  `folder`, ...) and of procedures (`autofocus`) belong to each driver. Look
  them up with `get_state`, `get_acquisition_settings` and `get_procedures`,
  and put them at the top of your workflow, so moving to another microscope
  means editing a few lines in one place:

  ```python
  # The names this microscope uses. Check them with get_state() and
  # get_acquisition_settings() when you move to another microscope.
  OVERVIEW = {"objective": 1, "laser_power": 10.0}
  DETAIL = {"objective": 3, "laser_power": 10.0}
  STACK = {"z_planes": 5, "z_step_um": 2.0}
  ```

- **Do not rely on a driver's extras.** A driver may add keys of its own to
  any answer, such as a serial number or a channel name. They are useful to
  read, but a workflow that needs them runs only on that microscope.
- **Check `success`.** Every command answers `{"success": ..., "content": ...}`.
  `success: False` means the driver could not do or could not confirm what
  you asked; the reason is in the content. Decide what your workflow should do
  then, rather than carrying on as if it had worked.
- **Let errors stop the run.** When carrying on would be unsafe, the driver
  raises an error instead of answering. Do not catch and ignore these: a
  workflow that keeps moving after a failed move can end up somewhere you did
  not plan.

## Where the files go

Every driver names the files after the `position_label` you pass to
`acquire`, inside the folder that `get_info()["content"]["output_root"]`
reports. Choose labels that tell you later what each picture was:
`tile_03`, `cell_12`, `well_B07`. Labelling the same position twice never
overwrites the first picture; the mock, for example, adds `_001` to the second.

Any further grouping is an acquisition setting that the driver offers, if it
offers one. The mock and the ZMART drivers offer `folder`, which puts the
files of one round in a folder of their own:

```python
zmart_controller.acquire(
    position_label="tile_03",
    acquisition_settings={"folder": "overview"},
)
```

Check with `get_acquisition_settings()` whether a driver offers it, and keep
the name with the others at the top of your workflow.

## Reading the saved images

The content of `acquire` holds `planes`, one entry for each saved picture:

| Key | What it is |
|---|---|
| `path` | the file the picture is in; one of `files` |
| `c`, `z`, `t` | which channel, depth and moment it is, each counted from 0 |
| `x_um`, `y_um` | the stage position the picture was taken at, in micrometres |
| `z_um` | the height of this picture, in micrometres |

The stage position is the centre of the picture. To turn a pixel into a stage
position, start from the centre and step by the pixel size, remembering that
right is +x and down is +y:

```python
x_um = plane["x_um"] + (column - (width - 1) / 2) * pixel_size_um
y_um = plane["y_um"] + (row - (height - 1) / 2) * pixel_size_um
```

The pixel size is in the file itself: OME-TIFF and OME-Zarr store it as
`PhysicalSizeX` and `PhysicalSizeY`. Reading it from the file keeps the
workflow portable, because every objective and every microscope has its own.
The [tutorial](tutorial.md#step-4-find-the-spots) shows this with
[tifffile](https://pypi.org/project/tifffile/).

A z-stack gives one entry per depth, each with its own `z_um`, and a picture
with several channels gives one per channel. Several entries can name the same
file when the driver saves a whole stack in one file; `c`, `z` and `t` then
say where inside it each picture is.

## When something goes wrong

- **`ValueError`**: the request was wrong, for example a setting name this
  microscope does not know, or a position outside the limits. The message
  names it; the matching `get_*` command shows what is allowed.
- **`RuntimeError`**: the microscope failed or refused, for example a move
  that could not be confirmed. Look at the microscope before running again.
- **`success: False`** with a reason in the content: the driver could not
  confirm a setting or an acquisition, but it is safe to carry on. Your
  workflow decides whether to try again, skip that position, or stop.
- **`no active microscope`**: no driver is plugged in, or the connection was
  closed. Run `set_instrument(...)` again; a notebook kernel restart closes it.

## Good to know

- **One step at a time.** Every command returns when the driver has finished,
  so a workflow reads from top to bottom like the experiment itself.
- **Call through the module.** Write `zmart_controller.set_xyz(...)` each
  time. A command saved in a variable keeps pointing at the old microscope
  after you plug in another one.
- **Several microscopes at once.** Hold a session for each, as part 2
  describes, and call the commands on the session instead of the module.
- **Begin and end cleanly.** Start with `set_instrument` and end with
  `disconnect()`, also when the run stops early; a `try` / `finally` around
  the workflow does that for you.
- **Keep the analysis separate.** Write the analysis as a function that takes
  the saved pictures and returns positions in micrometres. You can then test
  it on pictures you already have, without any microscope at all.
- **Save the plan with the pictures.** Writing the settings and positions of
  a run to a small file in `output_root` makes the experiment easy to review
  and to repeat.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
