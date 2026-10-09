# Using the ZMART-controller

## Contents

1. [Overview of the calls](#1-overview-of-the-calls)
2. [More information about the calls](#2-more-information-about-the-calls)

For a hands-on, step-by-step walk-through with a driver that simulates a
microscope, go to [this tutorial](tutorial.ipynb).

## 1) Overview of the calls

```python
from zmart_controller import mic

# 1) See which drivers are installed and how each connects, then connect to one
mic.get_instruments()
mic.connect(driver, connection=None)

# 2) Learn about the connected setup in more detail
mic.get_info()

# 3) Discover the motors, where you are in xyz space, and change the position
mic.get_actuators()
mic.get_xyz(with_actuators=None)
mic.set_xyz(x, y, z, with_actuators=None)

# 4) Capture the instrument state, and apply it again later with optional changes
#    (the state is not standardised and differs between microscopes; capturing it
#    and applying it again is what keeps a workflow interoperable)
mic.get_state()
mic.set_state(state)

# 5) Capture and save an image with the appropriate acquisition settings
mic.get_acquisition_settings()
mic.acquire(position_label, acquisition_settings=None)

# 6) Run a routine the microscope offers (for example autofocus)
#    (the routines are not standardised either and differ between microscopes)
mic.get_procedures()
mic.run_procedure(procedure)

# 7) Close the connection
mic.disconnect()
```

## 2) More information about the calls

Below is more information about the input and output of the individual calls. The outputs shown are the `content` of the answer; the values are examples, and on your microscope they will differ.

Every call waits for the microscope. It returns only when the driver has finished.

### mic.get_instruments()

```python
mic.get_instruments()
```

- **Input:** none
- **Output (example)**

  ```python
  {'mock': {},
   'my-scope': {'microscope': 'my-scope-room-12',
                'api_type': 'socket',
                'host': '192.168.1.20',
                'config': 'C:/vendor/settings.cfg'}}
  ```

- **Note:** One entry per installed driver, under the name you connect with. The value is the driver's connection details from its `zmart_driver.json`, without its password. The mock has none, so its entry is empty.

### mic.connect()

```python
mic.connect(driver, connection=None)
```

- **Input**
  - `driver`: a name from `get_instruments`
  - `connection`: optional; a dictionary handed to the driver unchanged, replacing the one from its `zmart_driver.json`
- **Output**

  ```python
  a connected controller; every command below is a method on it
  ```

### mic.get_info()

```python
mic.get_info()
```

- **Input:** none
- **Output (example)**

  ```python
  {'description': 'An inverted widefield microscope in room 12. The stage moves x and y, '
                  'the focus drive moves z; all three are in micrometres from the origin, '
                  'and +z moves the objective towards the sample. Objectives: slot 1 is '
                  '10x/0.30 air, slot 2 is 20x/0.75 air, slot 3 is 63x/1.40 oil. Channels: '
                  'DAPI, GFP and TxRed, each with its own exposure in milliseconds and '
                  'LED power in percent.'}
  ```

- **Note:** A description of the microscope, written by the driver's author. It tells you what the settings mean and which way the axes run, so read it once when you meet a new microscope.

### mic.get_actuators()

```python
mic.get_actuators()
```

- **Input:** none
- **Output (example)**

  ```python
  {'x': ['motoric'], 'y': ['motoric'], 'z': ['motoric', 'piezo']}
  ```

### mic.get_xyz()

```python
mic.get_xyz(with_actuators=None)
```

- **Input**
  - `with_actuators`: optional; the motor to read per axis, such as `{"z": "piezo"}`; an axis left out uses the first motor from `get_actuators`
- **Output (example)**

  ```python
  {'x': {'position': 0.0, 'unit': 'micrometer', 'actuators': {'motoric': 50000.0},               'canvas': [-5032.0, 5032.0]},
   'y': {'position': 0.0, 'unit': 'micrometer', 'actuators': {'motoric': 37500.0},               'canvas': [-5032.0, 5032.0]},
   'z': {'position': 0.0, 'unit': 'micrometer', 'actuators': {'motoric': 5000.0, 'piezo': 0.0},  'canvas': [-500.0, 500.0]}}
  ```

- **Note:** The answer is one dictionary with the keys `x`, `y` and `z`. Each axis has the same four entries. All numbers are in micrometres.
  - `position`: the position of the view in the absolute coordinate system. In a saved image, right is +x and down is +y.
  - `unit`: `'micrometer'`, the unit of every number in the answer, given as information.
  - `actuators`: the raw reading of each motor on this axis, as the microscope reports it. On an axis with several motors, the readings show how the motors share the position.
  - `canvas`: `[min, max]`, the range along this axis in which an image can be taken: the stage travel plus half a field of view.

### mic.set_xyz()

```python
mic.set_xyz(x, y, z, with_actuators=None)
```

- **Input**
  - `x`, `y`, `z`: the position to move to, in micrometres from the origin; all three always given
  - `with_actuators`: optional; the motor to use per axis; an axis left out uses the first motor from `get_actuators`
- **Output (example)**

  ```python
  {'x': {'position': 100.0, 'unit': 'micrometer', 'actuators': {'motoric': 50100.0},               'canvas': [-5032.0, 5032.0]},
   'y': {'position': 50.0,  'unit': 'micrometer', 'actuators': {'motoric': 37550.0},               'canvas': [-5032.0, 5032.0]},
   'z': {'position': 0.0,   'unit': 'micrometer', 'actuators': {'motoric': 5000.0, 'piezo': 0.0},  'canvas': [-500.0, 500.0]}}
  ```

- **Note:** The answer has the same form as the answer of `get_xyz`. It is read from the microscope after the stage has arrived, so it reports the actual position, not the requested one. A move outside the travel, or a move the driver could not confirm, returns `success: False`.

### mic.get_state()

```python
mic.get_state()
```

- **Input:** none
- **Output (example)**

  ```python
  {'changeable': {'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0, 'objective': 1},
   'observed': {'objective': '10x/0.30 Air', 'pixel_size': {'x': 1.0, 'y': 1.0, 'unit': 'um'}, ...}}
  ```

- **Note:** A snapshot of the settings. `changeable` is what `set_state` can apply; `observed` is read only. A state is a plain dictionary: save it with `json` and apply it again another day.

### mic.set_state()

```python
mic.set_state(state)
```

- **Input**
  - `state`: `{"changeable": {...}}` with some or all of the settings from `get_state`; the rest stay as they are
- **Output (example)**

  ```python
  {'applied': {'gain': 200.0}}
  ```

### mic.get_acquisition_settings()

```python
mic.get_acquisition_settings()
```

- **Input:** none
- **Output (example)**

  ```python
  {'format':    {'options': ['ome-tiff', 'ome-zarr'], 'active': 'ome-tiff'},
   'z_planes':  {'options': 'whole number from 1 up to the limit', 'active': 1},
   'z_step_um': {'options': 'number > 0', 'active': 1.0},
   ...}
  ```

- **Note:** The choices about how to capture and save. `options` says what a setting may be, `active` what is used when you say nothing.

### mic.acquire()

```python
mic.acquire(position_label, acquisition_settings=None)
```

- **Input**
  - `position_label`: the name of this position, such as `"A1"`; the saved files are named after it
  - `acquisition_settings`: optional; choices from `get_acquisition_settings`, such as `{"z_planes": 3, "z_step_um": 2.0}`
- **Output (example)**

  ```python
  {'position_label': 'A1',
   'files': ['/tmp/zmart-mock-output/A1.ome.tif', '/tmp/zmart-mock-output/A1.commands.json'],
   'planes': [{'path': '/tmp/zmart-mock-output/A1.ome.tif', 'c': 0, 'z': 0, 't': 0,
               'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}]}
  ```

- **Note:** Captures at the current position with the current settings, and saves. `files` lists every file saved; use those paths. `planes` says for every image plane which file, channel, depth and moment it is, and where on the sample it was taken. A second acquisition with the same label never overwrites the first.

### mic.get_procedures()

```python
mic.get_procedures()
```

- **Input:** none
- **Output (example)**

  ```python
  {'autofocus': {'description': 'Take a short z-stack around the current height, find the sharpest plane, and move there. Optional: range_um (default 20), step_um (default 2).'},
   ...}
  ```

### mic.run_procedure()

```python
mic.run_procedure(procedure)
```

- **Input**
  - `procedure`: `{"name": ..., ...}`; the name picks the routine, the other keys are its options
- **Output (example)**

  ```python
  {'ran': 'autofocus'}
  ```

### mic.disconnect()

```python
mic.disconnect()
```

- **Input:** none
- **Output:** nothing

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
