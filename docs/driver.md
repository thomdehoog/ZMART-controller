# Plug in your own driver functions

A driver is one Python function per command, collected in a dictionary and
handed to the controller. There is no base class to inherit from.
The mock microscope in [`tests/mock_zmart_driver/`](../tests/mock_zmart_driver/)
is a complete driver, built the way every ZMART driver is built inside; its
[README](../tests/mock_zmart_driver/README.md) walks through the parts. Read it
alongside this page, and copy its layout when you start a new driver.

## The shape

`connect` receives the connection dictionary and returns a *handle*: any object
you like that holds the live connection to your microscope. Every other
function receives that handle as its first argument. The controller never
looks inside the handle or any answer.

```
  connect(connection) --> handle --> get_xyz(handle, ...)
                                     set_xyz(handle, x, y, z, ...)
                                     acquire(handle, ...)
                                     ...
```

## A minimal driver

Two files in a folder called `zmart_controller/`:

```
my_driver/
    zmart_controller/
        zmart.json         # which instruments this driver serves
        __init__.py        # one function per command
    ...                    # the rest of the driver: vendor API, limits, calibration
```

`zmart.json` names the instruments. Three keys say which microscope;
anything else is handed to `connect` as it is:

```json
{
  "contract": 1,
  "instruments": [
    {"vendor": "acme", "microscope": "acme-5000", "api": "acme-sdk", "host": "localhost"}
  ]
}
```

`__init__.py` holds the functions, found by name:

```python
TRAVEL = {"x": (-5000.0, 5000.0), "y": (-5000.0, 5000.0), "z": (-500.0, 500.0)}
# Half the widest field (x, y) and half the deepest stack (z) this microscope takes.
HALF_PICTURE = {"x": 650.0, "y": 650.0, "z": 100.0}


def connect(connection):
    client = MyVendorClient(host=connection["host"])
    # The origin is this driver's configuration: saved once by its own setup
    # step, and loaded here every time the microscope connects.
    return {"client": client, "origin": load_saved_origin()}


def get_xyz(handle, *, with_actuators=None):
    raw = handle["client"].read_position()
    position = {
        axis: {
            "value": raw[axis] - handle["origin"][axis],
            "actuator": "motoric",
            "unit": "um",
            "range": [lo - handle["origin"][axis], hi - handle["origin"][axis]],
            "reach": [
                lo - handle["origin"][axis] - HALF_PICTURE[axis],
                hi - handle["origin"][axis] + HALF_PICTURE[axis],
            ],
        }
        for axis, (lo, hi) in TRAVEL.items()
    }
    return {"success": True, "content": position}


# ... and get_info, get_actuators, set_xyz, get_state, set_state,
#     get_acquisition_settings, acquire, get_procedures, run_procedure.
#     disconnect is optional.
```

Plug it in once on the microscope computer with
`zmart_controller.register_driver("path/to/my_driver")`. The controller reads
`zmart.json`, picks the functions by name, registers each instrument, and
remembers the driver for later sessions. A missing function or a wrong file is
refused at once, by name.

The three identity keys must name your instrument and no other. An operator
picks a microscope from the list by that name, so a second driver that claimed
a name already taken would quietly be driven in its place. The controller
therefore refuses a different driver asking for a name another driver holds,
and names both folders; plugging the same driver in again is harmless.

## Does it fit?

Once the driver connects, let the controller check the answers:

```python
import zmart_controller

problems = zmart_controller.validate_driver(instrument)
```

It calls every `get_*` function and compares each answer's content with the contract
below. The answer is a list of problems in plain words; an empty list means
the driver fits. It moves nothing and acquires nothing.

Because it acquires nothing, it cannot check `acquire`. Do that in your
driver's own tests, after an acquisition on a simulator or a test bench:

```python
answer = session.acquire(position_label="A1")
assert zmart_controller.check_acquire_answer(answer) == []
```

## The contract

Every function except `connect` and `disconnect` returns
`{"success": bool, "content": ...}`. The table gives what the `content` must
contain, so that an experiment written for one microscope keeps working on
another. A driver may add extra keys to any content; it should not leave out the
ones listed here.

| Function | Receives | The `content` must contain |
|---|---|---|
| `connect` | the connection dictionary | *(returns a handle: anything)* |
| `disconnect` *(optional)* | handle | *(returns nothing; afterwards every other call raises `RuntimeError`, and a second `disconnect` is harmless)* |
| `get_info` | handle | `output_root`, the folder where images are saved; and, recommended, `description` |
| `get_actuators` | handle | `{axis: [actuator names]}` for `x`, `y`, `z` |
| `get_xyz` | handle, `with_actuators=` | `{axis: {"value", "actuator", "unit", "range", "reach"}}` for `x`, `y`, `z`; `value`, `range` (`[min, max]`, how far the axis can travel) and `reach` (`[min, max]`, everywhere a picture can show on that axis; see below) in micrometers from the origin |
| `set_xyz` | handle, `x`, `y`, `z`, `with_actuators=` | `position` and `actuators`; raise if the move cannot be confirmed |
| `get_state` | handle | `{"changeable": {...}, "observed": {...}}` |
| `set_state` | handle, state | what was applied; act on `changeable` only |
| `get_acquisition_settings` | handle | `{name: {"options": [...], "active": value}}` |
| `acquire` | handle, `position_label=`, `acquisition_settings=` | `position_label`; `files`, a list with the path of every file the acquisition saved; and `planes`, one entry per saved image plane (see below) |
| `get_procedures` | handle | `{name: {"description", ...}}` |
| `run_procedure` | handle, `{"name": ..., ...}` | `ran`, the name of the procedure; raise `ValueError` for an unknown name |

`reach` is the area a picture can cover. The stage stops at the end of its
travel, but a picture taken there still shows half a field beyond it, and a
z-stack started at the top or bottom of the focus can reach half a stack
further. So `reach` is the travel widened by half the largest field the driver
can take (for x and y) and half the deepest stack (for z), and it always
contains `range`. When the stage, or the limits, keep every picture inside the
travel on some axis, `reach` equals `range` there. The driver works it out from
what it knows: its objectives, its camera and its stack limits. The interface
and the viewer use it to lay out the whole specimen area before the first
picture is taken, so nothing has to grow or shift once pictures arrive.

The positions and the pictures share one frame, the one in which you observe
the specimen: in a saved image, **right is +x and down is +y**. A picture
taken further along +x shows the part of the specimen that lay to its right.
The driver arranges this, whatever way the camera or the stage is mounted, so
that "left", "right", "up" and "down" mean the same on every microscope, to a
person reading the images and to anything that drives the stage from them.
Which way +z points (towards the objective or away from it) is the
microscope's own; a driver says so in its `description`.

`files` lists everything the acquisition saved: the images, and any file the
driver saved beside them for this acquisition. A format kept as a folder, such
as OME-Zarr, is listed by its folder. The name is fixed so that a workflow
finds the pictures on any microscope: one written for a Leica keeps working on
a Nikon only if both say where their images are in the same words. Every path
must exist when `acquire` returns. An acquisition that did not succeed may
list none.

The driver names the files after `position_label`. Anything else about where
they go is the driver's choice; if a person should be able to choose, offer it
as an acquisition setting, the way the mock offers `folder`. A workflow never
has to guess the path, because `files` tells it.

`planes` says where each saved picture sits on the sample. A file says how
large a pixel is, but rarely where the stage stood, and a stack is taken with
the stage at one place while its planes are spread above and below it. Only the
driver knows, at the moment it acquires, so it says so here. That is what lets
the operator page lay every picture down in its place, and lets a workflow tell
one channel or depth from another, on any microscope. Each entry describes one
image plane, a single picture of one channel at one depth and one moment:

| Key | What it is |
|---|---|
| `path` | the file the plane is in; one of `files` |
| `c` | which channel, counted from 0 in the order the microscope records them |
| `z` | which depth of the stack, counted from 0 from the first plane taken; 0 for a single plane |
| `t` | which moment, counted from 0; 0 for an acquisition taken once |
| `x_um`, `y_um` | the stage position the plane was taken at, in micrometres, in the frame `get_xyz` and `set_xyz` use |
| `z_um` | the height of this plane, in micrometres, in the same frame |

When a file holds many planes, such as a stack saved as one file, every plane
names that file, and `c`, `z` and `t` say where inside it the plane is. No two
planes may share the same `c`, `z` and `t`. A position the driver genuinely
cannot know is `None` rather than a guess, because a picture laid down in the
wrong place is worse than one left unplaced. A driver may add entries of its
own to a plane, such as a channel's name; they are extras that nothing relies
on, so a workflow that should run on any microscope must not need them.

A *state* has two parts. `"changeable"` holds the settings that `set_state`
applies. `"observed"` is a read-only description, such as which objective is in
place and the pixel size; it is never used as an instruction. When the allowed
values of a setting cannot be listed, `"options"` may be a short description
such as `"float > 0"`.

`description` is the microscope in plain words, for whoever drives it: a
person, a notebook, or the ZMART AI agent, which learns the instrument from it.
Say what the other answers cannot: what each setting in `changeable` means, its
unit and its bounds, which objective sits in which slot, and anything about the
sample or the images worth knowing. Leave out what `get_xyz` and
`get_procedures` already report, since those stay current and a description
does not. A driver without a description still works with the controller and
in every experiment; only the AI agent then has less to go on. When it is
there, it must be text with something in it.

Anything else in `get_info` is an extra of your driver; an experiment that
depends on it will not run elsewhere.

## Rules

- **Refuse by raising; report soft outcomes.** When carrying on would be
  unsafe, raise: `ValueError` when the request itself is wrong (an unknown
  option, a position outside the limits), `RuntimeError` when the microscope
  fails or refuses. The controller passes your error to the user unchanged.
  Use `success: False` only for outcomes it is safe to carry on from, and say
  what happened in the `content`.
- **Say when a change could not be confirmed.** Microscope software often
  accepts a command before it has happened, so read back to check. When a
  setting or an acquisition was sent but the readback never showed it, answer
  `success: False` with `"confirmed": False` and the reason in the `content`.
  A move is the exception: `set_xyz` raises `RuntimeError`, because carrying
  on at an unknown position is never safe.
- **Use full import paths in the plugin folder.** The controller loads
  `zmart_controller/__init__.py` under a name of its own, so that two drivers
  can never clash. A relative import such as `from .. import commands` then
  cannot find the rest of your driver; write `from my_driver import commands`
  instead.
- **Reject what you do not understand.** An unknown option name or procedure
  raises `ValueError`. A typo that is silently ignored can cost someone an
  entire experiment.
- **Keep secrets out of error messages.** The connection dictionary may hold
  passwords. Name the keys, never the values.
- **Keep safety and configuration in the driver.** Travel limits, the origin,
  calibration: only the driver knows the hardware. Save them in the computer's
  configuration folder, never in a repository, and load them in `connect`.
- **Test against the mock's tests.** The tests in [`tests/`](../tests/) show the
  behaviour a workflow relies on; running your driver through the same
  scenarios is the quickest way to find gaps.

## Shipping it as a package

A driver that is its own package can be found without `register_driver`: one
line in its `pyproject.toml` names the function to call, and the controller
calls it the first time `get_instruments()` runs.

```toml
[project.entry-points."zmart_controller.drivers"]
acme = "zmart_drivers.acme:register"
```
