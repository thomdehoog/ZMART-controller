# 1. Using the ZMART-controller

## Contents

1. [Overview of the calls](#1-overview-of-the-calls)
2. [More information about the calls](#2-more-information-about-the-calls)

For a step-by-step walk-through on the mock driver, the simulated microscope
that comes with the controller, open the [tutorial notebook](tutorial.ipynb).

## 1) Overview of the calls

```python
import zmart_controller

# 1) See which drivers are installed and how each connects, then connect to one
zmart_controller.get_instruments()
mic = zmart_controller.ZmartController("mock")

# 2) Learn about the connected setup: where images go, and the microscope in plain words
mic.get_info()

# 3) Discover the motors, then read the position and where pictures can show, or move (micrometres)
mic.get_actuators()
mic.get_xyz()
mic.set_xyz(x, y, z, with_actuators=Dict)

# 4) Capture the instrument settings, and apply them again later
mic.get_state()
mic.set_state(Dict)

# 5) Capture and save an image with the current settings and position
mic.get_acquisition_settings()
mic.acquire(position_label=String, acquisition_settings=Dict)

# 6) Run a routine the microscope offers (for example autofocus)
mic.get_procedures()
mic.run_procedure(Dict)

# 7) Close the connection
mic.disconnect()
```

## 2) More information about the calls

The answers below are real answers from the mock, trimmed where they are
long. On another microscope the numbers differ; the keys shown are the same
on every microscope, and anything else is an extra of that driver.

#### get_instruments

```python
zmart_controller.get_instruments()
# {'mock': {}, 'stellaris': {'microscope': 'stellaris5-room-42', 'host': ..., ...}}
```

The drivers installed on this computer, each with how it connects, without
its password. The mock is always there.

#### ZmartController

```python
mic = zmart_controller.ZmartController("mock")
mic = zmart_controller.ZmartController("mock", {"output_root": "my_images"})
```

Making the controller connects. The name comes from `get_instruments`. The
optional dictionary is handed to the driver unchanged and replaces the
connection from its `zmart_driver.json`; the mock takes `output_root`,
`mock_timing` (`"instant"` for quick tests) and `token`.

#### get_info

```python
mic.get_info()["content"]
# {'output_root': '/tmp/zmart-mock-output',
#  'description': 'A pretend widefield fluorescence microscope ...'}
```

`output_root` is where the driver saves images. `description` is the
microscope in plain words: what each setting means, its unit and bounds,
which objective sits in which slot, which way +z points. Read it once when
you meet a new microscope.

#### get_actuators

```python
mic.get_actuators()["content"]
# {'x': ['motoric'], 'y': ['motoric'], 'z': ['motoric', 'piezo']}
```

The motors that can move each axis. Pick one per axis with
`with_actuators={"z": "piezo"}` on `get_xyz` and `set_xyz`; an axis left
out uses the first one.

#### get_xyz

```python
mic.get_xyz()["content"]
# {'x': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-5032.0, 5032.0]},
#  'y': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-5032.0, 5032.0]},
#  'z': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-500.0, 500.0]}}
```

Positions are micrometres from the origin, a point saved once for this
microscope, so a position means the same place on the sample every time.
In a saved image, right is +x and down is +y. The canvas is everywhere a
picture can show: the travel plus half a field of view. Plan positions
inside it.

#### set_xyz

```python
mic.set_xyz(100, 50, 0)["content"]
# {'position': {'x': 100, 'y': 50, 'z': 0},
#  'actuators': {'x': 'motoric', 'y': 'motoric', 'z': 'motoric'}}

mic.set_xyz(99999, 0, 0)
# {'success': False, 'content': 'ValueError: move refused: x would go to ... outside the travel ...'}
```

Move to a position in micrometres from the origin. All three axes are
always given. When the answer comes back, the stage has arrived; a move
outside the travel, or one the driver could not confirm, is `success: False`.

#### get_state

```python
mic.get_state()["content"]
# {'changeable': {'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0, 'objective': 1},
#  'observed': {'objective': '10x/0.30 Air', 'pixel_size': {'x': 1.0, 'y': 1.0, 'unit': 'um'}, ...}}
```

A snapshot of the settings. `changeable` is what `set_state` can apply;
the `description` explains each one. `observed` is read only. A state is a
plain dictionary: save it with `json` and apply it again another day.

#### set_state

```python
mic.set_state({"changeable": {"gain": 200.0}})["content"]
# {'applied': {'gain': 200.0}}
```

Apply some or all of the `changeable` settings; the rest stay as they are.
An unknown name or a value outside the limits is `success: False`, so a
typo never passes silently.

#### get_acquisition_settings

```python
mic.get_acquisition_settings()["content"]
# {'format':   {'options': ['ome-tiff', 'ome-zarr'], 'active': 'ome-tiff'},
#  'z_planes': {'options': 'whole number from 1 up to the limit', 'active': 1},
#  'z_step_um': {'options': 'number > 0', 'active': 1.0},
#  ...}
```

The choices about how to capture and save, as opposed to the microscope's
settings in the state. `options` says what a setting may be, `active` what
is used when you say nothing.

#### acquire

```python
answer = mic.acquire(position_label="A1")
answer["content"]
# {'position_label': 'A1',
#  'files': ['/tmp/zmart-mock-output/A1.ome.tif', '/tmp/zmart-mock-output/A1.commands.json'],
#  'planes': [{'path': '/tmp/zmart-mock-output/A1.ome.tif', 'c': 0, 'z': 0, 't': 0,
#              'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}]}

mic.acquire(position_label="cell 1", acquisition_settings={"z_planes": 3, "z_step_um": 2.0})
```

Capture at the current position with the current settings, and save.
`files` lists every file saved, so use those paths rather than building your
own. `planes` says for every image plane which file, channel, depth and
moment it is, and where on the sample it was taken. A second acquisition
with the same label never overwrites the first.

#### get_procedures

```python
mic.get_procedures()["content"]
# {'autofocus': {'description': 'Take a short z-stack around the current height, find the sharpest plane, and move there. Optional: range_um (default 20), step_um (default 2).'},
#  ...}
```

The routines this microscope offers, each with a description that says what
it does and which options it takes.

#### run_procedure

```python
mic.run_procedure({"name": "autofocus", "range_um": 10, "step_um": 1})["content"]
# {'ran': 'autofocus'}
```

Run one by name; the other keys are its options. An unknown name is
`success: False`.

#### disconnect

```python
mic.disconnect()
```

Close the connection. To drive the microscope again, make a new controller.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
