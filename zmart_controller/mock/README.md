# The mock driver

The mock driver lets you try every ZMART command without a microscope. It is
built from the same parts as every ZMART driver, so you can read it to learn
how a driver works inside, and copy its layout when you start your own.

Underneath it runs **MockScope Control**, pretend vendor software with a
pretend microscope behind it (see [`testing/mock_api/`](testing/mock_api/README.md)).
MockScope behaves like real vendor software: it speaks its own language,
takes time to move, refuses commands while busy, writes its own file format,
and can be made to fail on purpose. Everything in this driver above it is
the same code a real driver would need.

## Try it

```python
import zmart_controller

mic = zmart_controller.ZmartController(zmart_controller.mock)

mic.set_xyz(100, 50, 0)
answer = mic.acquire(position_label="A1")
answer["content"]["files"]  # real OME-TIFF files you can open in Fiji or napari
answer["content"]["planes"]  # for each picture: its file, channel, depth and stage position
```

The pictures show a slide of small bright spots, like fluorescent beads.
Move the stage and the spots move; change the focus and they blur.

Images are saved under the system's temporary folder unless the connection
dictionary names an `output_root`. Two more connection entries are useful while
experimenting: `"mock_timing": "instant"` makes every move and acquisition
finish at once, and `"token"` is the pretend login (`"mock-token"`). For example:

```python
mic = zmart_controller.ZmartController(
    zmart_controller.mock, {"output_root": "mock-images", "mock_timing": "instant"}
)
```

## The parts

The driver follows the anatomy of a ZMART driver, described in full in
[the anatomy of a ZMART driver](https://github.com/thomdehoog/ZMART-drivers/blob/main/docs/driver-anatomy.md).
Each part is a folder. The parts build on one another in the order of the
table: the vendor interface at the bottom knows only the vendor software, and
the functions the controller calls at the top only put the other parts to
work.

| Folder | Part | What it does here |
|---|---|---|
| [`vendor_interface/`](vendor_interface/) | 1. Vendor interface | Starts MockScope, logs in, and offers one plain function (a *primitive*) per vendor command. The only part that knows MockScope. Its `errors.py` sorts every error MockScope raises into one of the shared kinds (temporary, bad request, permanent, connection lost). |
| [`dispatcher/`](dispatcher/) | 2. Dispatcher | The engines that run an action safely, the same for every microscope. `read.py` runs a reading: one read at a time, a few tries after a temporary problem, a time limit, and "unknown" rather than a guess. `change.py` runs a change: the limits gate (`gate.py`), sending, retries, reading back to confirm, sending again, and giving up softly when it cannot confirm. `rules.py` says what each engine does for each kind of problem, and `tuning.py` holds the retries and time windows. |
| [`actions/`](actions/) | 3. Actions | What the driver asks the microscope, as short definitions the dispatcher runs: `get.py` holds the readings (which primitive, what the value means) and `set.py` the changes (which primitive, how to confirm it). |
| [`procedures/`](procedures/) | 4. Procedures | Recipes built only from actions: autofocus, backlash takeup, parking the piezo, and recording the origin. |
| [`data_handling/`](data_handling/) | 5. Data handling | Waits for the vendor's file, turns the picture to line up with the stage, writes OME-TIFF or OME-Zarr, and saves the log of the commands behind it. |
| [`configuration/`](configuration/) | 6. Configuration | The machine description, image-to-stage registration, origin, limits and optical calibration, each with shipped defaults and a check. Also the arithmetic between stage and user coordinates. |
| [`zmart_controller_plugin.py`](zmart_controller_plugin.py) | 7. The functions the controller calls | One function per command, plus `disconnect`. They only map commands onto the parts listed before them. [`__init__.py`](__init__.py) imports them, which is how the controller finds them. |
| [`testing/`](testing/) | 8. Testing | The mock API, MockScope Control. The mock driver's own tests are in the repository's [`tests/mock_tests/`](../../tests/mock_tests/). |

## How a move travels through the driver

`zmart_controller.set_xyz(100, 50, 0)` goes through these steps:

1. **`zmart_controller_plugin.py`** picks the motor for each axis and hands the request to the
   set action for a move.
2. **The set action** (`actions/set.py`) reads the current position through
   the reading engine, and turns the user position (micrometres from the
   origin) into a stage position, using the configuration.
3. **The change engine** (`dispatcher/change.py`) asks the limits gate. A position outside the
   limits is refused here, before anything is sent.
4. It waits until the microscope is not busy, then **sends** the move
   through the vendor interface.
5. If MockScope answers "busy", the vendor interface's `errors.py` sorts that
   as temporary, and the **rules** say to send again after a short pause.
6. The dispatcher **reads back** the position until it matches the target.
   If it never does, `set_xyz` raises `RuntimeError`, because carrying on
   at an unknown position is never safe.

Every step writes a line to the command log, which is saved next to the
images of each acquisition.

## Setting the microscope up

On a real microscope, the operator runs a setup step once, and the driver
saves the result in the computer's configuration folder. The mock works the
same way, through `zmart_controller.mock.configuration.save` and
`zmart_controller.mock.procedures.record_origin`. Until something is saved, the
shipped defaults are used, one `default.json` in each item's folder under
[`configuration/`](configuration/), and `get_info()` says so.

The defaults are deliberately the defaults of an *uncalibrated* microscope.
The registration assumes the camera is mounted straight, and the
calibration assumes the objectives line up perfectly. MockScope's real
camera is mirrored and its objectives are slightly offset, just as a real
microscope would be, so there is something real to measure.
`scope.truth()` holds the right answers for checking.
