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

Below is more information about the input and output of each call.

Every call answers with the same two keys. `success` is `True` or `False`. `content` is the answer itself when it worked, or a message that says what went wrong. Check `success` first, then use `content`:

```python
answer = mic.get_xyz()
if answer["success"]:
    position = answer["content"]
else:
    print(answer["content"])
```

The values in the examples below are from the mock. On your microscope they will be different.

Every call waits for the microscope. It returns when the driver is done.

<br>

### mic.get_instruments()

```python
mic.get_instruments()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'content': {'mock': {},
               'my-scope': {'microscope': 'my-scope-room-12',
                            'api_type': 'socket',
                            'host': '192.168.1.20',
                            'config': 'C:/vendor/settings.cfg'}}}
  ```

- **Note:** One entry per installed driver. The key is the name you use in `connect`. The value is the connection from the driver's `zmart_driver.json`, without the password. The mock needs no connection, so its entry is empty.

<br>

### mic.connect()

```python
mic.connect(driver, connection=None)
```

- **Input**
  - `driver`: a name from `get_instruments`
  - `connection`: optional; a dictionary that is passed to the driver as it is. Default: the `connection` from the driver's `zmart_driver.json`.
- **Output:** nothing. After this call, every command below goes to that microscope.

<br>

### mic.get_info()

```python
mic.get_info()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'content': {'description': 'An inverted widefield microscope in room 12. The stage moves x and y, '
                              'the focus drive moves z; all three are in micrometres from the origin, '
                              'and +z moves the objective towards the sample. Objectives: slot 1 is '
                              '10x/0.30 air, slot 2 is 20x/0.75 air, slot 3 is 63x/1.40 oil. Channels: '
                              'DAPI, GFP and TxRed, each with its own exposure in milliseconds and '
                              'LED power in percent.'}}
  ```

- **Note:** A description of the microscope, written by the driver's author. It explains the settings and the axes. Read it once when you start on a new microscope.

<br>

### mic.get_actuators()

```python
mic.get_actuators()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'content': {'x': ['motoric'], 'y': ['motoric'], 'z': ['motoric', 'piezo']}}
  ```

<br>

### mic.get_xyz()

```python
mic.get_xyz(with_actuators=None)
```

- **Input**
  - `with_actuators`: optional; which motor to read per axis, for example `{"z": "piezo"}`. Default: the first motor in `get_actuators` for each axis.
- **Output (example)**

  ```python
  {'success': True,
   'content': {'x': {'position': 0.0, 'unit': 'micrometer', 'actuators': {'motoric': 50000.0},               'canvas': [-5032.0, 5032.0]},
               'y': {'position': 0.0, 'unit': 'micrometer', 'actuators': {'motoric': 37500.0},               'canvas': [-5032.0, 5032.0]},
               'z': {'position': 0.0, 'unit': 'micrometer', 'actuators': {'motoric': 5000.0, 'piezo': 0.0},  'canvas': [-500.0, 500.0]}}}
  ```

- **Note:** One dictionary with the keys `x`, `y` and `z`. Each axis has the same four entries. All numbers are in micrometres.
  - `position`: the position of the view in the absolute coordinate system. In a saved image, right is +x and down is +y.
  - `unit`: `'micrometer'`. This is the unit of every number in the answer. It is given as information.
  - `actuators`: the raw reading of each motor on this axis, as the microscope reports it. When an axis has several motors, this shows how they share the position.
  - `canvas`: `[min, max]`. The range on this axis where an image can be taken. It is the stage travel plus half a field of view.

<br>

### mic.set_xyz()

```python
mic.set_xyz(x, y, z, with_actuators=None)
```

- **Input**
  - `x`, `y`, `z`: the position to move to, in micrometres from the origin. All three are required.
  - `with_actuators`: optional; which motor to use per axis, for example `{"z": "piezo"}`. Default: the first motor in `get_actuators` for each axis.
- **Output (example)**

  ```python
  {'success': True,
   'content': {'x': {'position': 100.0, 'unit': 'micrometer', 'actuators': {'motoric': 50100.0},               'canvas': [-5032.0, 5032.0]},
               'y': {'position': 50.0,  'unit': 'micrometer', 'actuators': {'motoric': 37550.0},               'canvas': [-5032.0, 5032.0]},
               'z': {'position': 0.0,   'unit': 'micrometer', 'actuators': {'motoric': 5000.0, 'piezo': 0.0},  'canvas': [-500.0, 500.0]}}}
  ```

- **Note:** The call returns when the stage has arrived. The answer is the same as `get_xyz`, read from the microscope. So it shows the real position, not the one you asked for. A move outside the travel returns `success: False`. So does a move the driver could not confirm.

<br>

### mic.get_state()

```python
mic.get_state()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'content': {'changeable': {'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0, 'objective': 1},
               'observed': {'objective': '10x/0.30 Air', 'pixel_size': {'x': 1.0, 'y': 1.0, 'unit': 'um'}, ...}}}
  ```

- **Note:** A snapshot of the settings, in two parts. `changeable` holds the settings that `set_state` can change. `observed` holds facts you can only read, such as the objective in use and the pixel size. The keys are not standardised. They differ between microscopes, and `get_info` explains them for yours. A state is a plain dictionary. You can save it as JSON and apply it again later.

<br>

### mic.set_state()

```python
mic.set_state(state)
```

- **Input**
  - `state`: `{"changeable": {...}}` with some or all of the settings from `get_state`. The rest stay as they are.
- **Output (example)**

  ```python
  {'success': True,
   'content': {'applied': {'gain': 200.0}}}
  ```

- **Note:** Only the settings you give are applied. All other settings keep their value. The answer lists what was applied, read back from the microscope.

<br>

### mic.get_acquisition_settings()

```python
mic.get_acquisition_settings()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'content': {'format':    {'options': ['ome-tiff', 'ome-zarr'], 'active': 'ome-tiff'},
               'z_planes':  {'options': 'whole number from 1 up to the limit', 'active': 1},
               'z_step_um': {'options': 'number > 0', 'active': 1.0},
               ...}}
  ```

- **Note:** The settings for taking and saving an image. `options` lists the values a setting can take. `active` is the value in use now. It is used when you give nothing.

<br>

### mic.acquire()

```python
mic.acquire(position_label, acquisition_settings=None)
```

- **Input**
  - `position_label`: a name for this position, for example `"A1"`. The files are saved under this name.
  - `acquisition_settings`: optional; values from `get_acquisition_settings`, for example `{"z_planes": 3, "z_step_um": 2.0}`. Default: the `active` value of every setting.
- **Output (example)**

  ```python
  {'success': True,
   'content': {'position_label': 'A1',
               'files': ['/tmp/zmart-mock-output/A1.ome.tif', '/tmp/zmart-mock-output/A1.commands.json'],
               'planes': [{'path': '/tmp/zmart-mock-output/A1.ome.tif', 'c': 0, 'z': 0, 't': 0,
                           'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}]}}
  ```

- **Note:** Takes an image at the current position with the current settings, and saves it to disk. `files` lists every saved file. `planes` lists every image plane, with its file, channel, depth, time point, and the sample position where it was taken. A second acquisition with the same label is saved as a new file. The first one is never overwritten.

<br>

### mic.get_procedures()

```python
mic.get_procedures()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'content': {'autofocus': {'description': 'Take a short z-stack around the current height, find the sharpest plane, and move there. Optional: range_um (default 20), step_um (default 2).'},
               ...}}
  ```

- **Note:** Each routine has a name and a description. The description says what the routine does, which options it takes, and their defaults.

<br>

### mic.run_procedure()

```python
mic.run_procedure(procedure)
```

- **Input**
  - `procedure`: a dictionary with the key `"name"` and the options of that routine, for example `{"name": "autofocus", "range_um": 30}`. An option you leave out takes the default from the description in `get_procedures`.
- **Output (example)**

  ```python
  {'success': True,
   'content': {'ran': 'autofocus'}}
  ```

<br>

### mic.disconnect()

```python
mic.disconnect()
```

- **Input:** none
- **Output:** nothing

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.

If the code in this repository inspires you, or you use it or build on it, please acknowledge it.
The [CITATION.cff](../../CITATION.cff) file says how to cite it.
