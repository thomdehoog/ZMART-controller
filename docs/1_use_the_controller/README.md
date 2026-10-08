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

The outputs are real answers from the mock, trimmed where they are long, shown as the `content` of the answer. On another microscope the values differ; the keys shown are the same on every microscope, and anything else is an extra of that driver.

### get_instruments

```python
zmart_controller.get_instruments()
```

- **Input:** none
- **Output**

  ```python
  {'mock': {}, 'stellaris': {'microscope': 'stellaris5-room-42', 'host': ..., ...}}
  ```

### ZmartController

```python
mic = zmart_controller.ZmartController(driver, connection=None)
```

- **Input**
  - `driver`: a name from `get_instruments`
  - `connection`: optional; a dictionary handed to the driver unchanged, replacing the one from its `zmart_driver.json`
- **Output**

  ```python
  a connected controller; every command below is a method on it
  ```

### get_info

```python
mic.get_info()
```

- **Input:** none
- **Output**

  ```python
  {'output_root': '/tmp/zmart-mock-output',
   'description': 'A pretend widefield fluorescence microscope ...'}
  ```

- **Note:** `output_root` is where the driver saves images. `description` is the microscope in plain words: what each setting means, its unit and bounds, which objective sits in which slot, which way +z points.

### get_actuators

```python
mic.get_actuators()
```

- **Input:** none
- **Output**

  ```python
  {'x': ['motoric'], 'y': ['motoric'], 'z': ['motoric', 'piezo']}
  ```

### get_xyz

```python
mic.get_xyz(with_actuators=None)
```

- **Input**
  - `with_actuators`: optional; the motor to read per axis, such as `{"z": "piezo"}`; an axis left out uses the first motor from `get_actuators`
- **Output**

  ```python
  {'x': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-5032.0, 5032.0]},
   'y': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-5032.0, 5032.0]},
   'z': {'value': 0.0, 'actuator': 'motoric', 'canvas': [-500.0, 500.0]}}
  ```

- **Note:** Positions are micrometres from the origin, a point saved once for this microscope; in a saved image, right is +x and down is +y. The canvas is everywhere a picture can show: the travel plus half a field of view.

### set_xyz

```python
mic.set_xyz(x, y, z, with_actuators=None)
```

- **Input**
  - `x`, `y`, `z`: the position to move to, in micrometres from the origin; all three always given
  - `with_actuators`: optional; the motor to use per axis; an axis left out uses the first motor from `get_actuators`
- **Output**

  ```python
  {'position': {'x': 100, 'y': 50, 'z': 0},
   'actuators': {'x': 'motoric', 'y': 'motoric', 'z': 'motoric'}}
  ```

- **Note:** When the answer comes back, the stage has arrived. A move outside the travel, or one the driver could not confirm, is `success: False`.

### get_state

```python
mic.get_state()
```

- **Input:** none
- **Output**

  ```python
  {'changeable': {'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0, 'objective': 1},
   'observed': {'objective': '10x/0.30 Air', 'pixel_size': {'x': 1.0, 'y': 1.0, 'unit': 'um'}, ...}}
  ```

- **Note:** A snapshot of the settings. `changeable` is what `set_state` can apply; `observed` is read only. A state is a plain dictionary: save it with `json` and apply it again another day.

### set_state

```python
mic.set_state(state)
```

- **Input**
  - `state`: `{"changeable": {...}}` with some or all of the settings from `get_state`; the rest stay as they are
- **Output**

  ```python
  {'applied': {'gain': 200.0}}
  ```

### get_acquisition_settings

```python
mic.get_acquisition_settings()
```

- **Input:** none
- **Output**

  ```python
  {'format':    {'options': ['ome-tiff', 'ome-zarr'], 'active': 'ome-tiff'},
   'z_planes':  {'options': 'whole number from 1 up to the limit', 'active': 1},
   'z_step_um': {'options': 'number > 0', 'active': 1.0},
   ...}
  ```

- **Note:** The choices about how to capture and save. `options` says what a setting may be, `active` what is used when you say nothing.

### acquire

```python
mic.acquire(position_label, acquisition_settings=None)
```

- **Input**
  - `position_label`: the name of this position, such as `"A1"`; the saved files are named after it
  - `acquisition_settings`: optional; choices from `get_acquisition_settings`, such as `{"z_planes": 3, "z_step_um": 2.0}`
- **Output**

  ```python
  {'position_label': 'A1',
   'files': ['/tmp/zmart-mock-output/A1.ome.tif', '/tmp/zmart-mock-output/A1.commands.json'],
   'planes': [{'path': '/tmp/zmart-mock-output/A1.ome.tif', 'c': 0, 'z': 0, 't': 0,
               'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}]}
  ```

- **Note:** Captures at the current position with the current settings, and saves. `files` lists every file saved; use those paths. `planes` says for every image plane which file, channel, depth and moment it is, and where on the sample it was taken. A second acquisition with the same label never overwrites the first.

### get_procedures

```python
mic.get_procedures()
```

- **Input:** none
- **Output**

  ```python
  {'autofocus': {'description': 'Take a short z-stack around the current height, find the sharpest plane, and move there. Optional: range_um (default 20), step_um (default 2).'},
   ...}
  ```

### run_procedure

```python
mic.run_procedure(procedure)
```

- **Input**
  - `procedure`: `{"name": ..., ...}`; the name picks the routine, the other keys are its options
- **Output**

  ```python
  {'ran': 'autofocus'}
  ```

### disconnect

```python
mic.disconnect()
```

- **Input:** none
- **Output:** nothing

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
