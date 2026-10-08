# ZMART Controller

[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](pyproject.toml)
[![tests](https://github.com/thomdehoog/ZMART-controller/actions/workflows/tests.yml/badge.svg)](https://github.com/thomdehoog/ZMART-controller/actions/workflows/tests.yml)
[![status](https://img.shields.io/badge/status-early%20use-orange)](#status)

<table>
<tr>
<td width="170"><img src="docs/zmart-controller-icon.png" width="150" alt="ZMART Controller"></td>
<td valign="middle">

The **ZMART Controller** provides a small, universal schema for driving a microscope from Python. Writing your automated workflow with its commands simplifies implementing, testing and simulating workflows. On top of this, when you build your workflow with this vocabulary, it runs on any microscope that has a ZMART driver for it. 

It is part of [**ZMART**](https://github.com/thomdehoog/ZMART-microscopy) (ZMB's Microscopy-Agnostic Research Toolkit), the tools we are building for smart microscopy at the Center for Microscopy and Image Analysis (ZMB), University of Zurich.

</td>
</tr>
</table>

## The Problem

When you want to implement an automated workflow on a microscope, you run into two problems:

1. **You need time on the microscope.** You can only build and test the workflow at the microscope itself,
   and microscope time is often limited.

2. **You want to share the workflow, but it only runs on your specific microscope.** Once it works, you want
   to report it and share it, so that others can review it and use it. But every microscope setup is different,
   with its own programming interface, so a workflow written for yours does not run on theirs. That makes your
   findings very hard to reproduce.


## The Solution

The ZMART controller sits between your workflow and the microscope. It addresses both problems:

1. **A universal interface.** Your workflow talks to the controller instead of to the microscope directly.
   Behind the controller you can plug in a simulated microscope, so you can build and test the whole
   workflow at your desk, and go to the microscope only once it works.

2. **A common vocabulary.** Every microscope speaks its own language. A ZMART driver translates that language
   into a short list of shared commands, so a workflow written once runs on every microscope that has a
   driver. The driver also keeps the microscope within its safe limits, and gives every microscope the same
   coordinates: the space in which you observe the specimen.

<p align="center">
  <img src="docs/zmart-controller-overview-2.png" width="100%" alt="Three microscopes, each with its own driver plugged in, connect through the ZMART Controller, one universal command vocabulary, to a script, an interface and an AI agent">
</p>

### The vocabulary

Everything you can say to a microscope:

```python
import zmart_controller

# 1) See which drivers are installed and how each connects, then connect to one
zmart_controller.get_instruments()
mic = zmart_controller.ZmartController(String)

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

`set_state` and `run_procedure` take one dictionary, and so do the `acquisition_settings` of
`acquire`. The keys come from the matching `get_` command, so a driver can offer whatever its
microscope can do without the vocabulary having to grow.

Every command except `disconnect` answers with the same two things:

```python
{"success": True, "content": {...}}
```

`success` says whether the driver did what you asked. `content` is whatever the
driver has to say about it: a position, a saved-file record, a state. When
something unexpected happens, the answer is `success: False`, and the details are in `content`.
We have not defined a vocabulary for error messages at this point.


## Want to give it a try?

1. **[Plug in a driver](docs/2_plug_in_a_driver/README.md).** What a driver is, what it must provide, where its functions go, and how to
   plug it in.
2. **[Use the controller](docs/1_use_the_controller/README.md).** Every command, what it does, and what it answers.

## Install it

Install the controller into your Python environment (Python 3.11 or newer; it needs nothing else):

```bash
pip install "git+https://github.com/thomdehoog/ZMART-controller"
```

To use it in a project of your own, add it to the project's dependencies, for example in its
`pyproject.toml`:

```toml
dependencies = ["zmart-controller @ git+https://github.com/thomdehoog/ZMART-controller"]
```

## Run the tests

The tests run on the mock driver, so they need no microscope:

```bash
pip install -e ".[test]"
python -m pytest
```

## Related standards

We are aware of the [useq-schema](https://github.com/pymmcore-plus/useq-schema) from the Micro-Manager
community and of Anthropic's [Model Hardware Standard](https://www.anthropic.com/news/model-hardware-standard-research-preview).
We might switch, because both have real upsides. Today the useq-schema is not interoperable enough for
our needs, and the Model Hardware Standard is not released to the public yet.

## Status

This is version 0.1. We do not use it daily yet, because our smart-microscopy workflows are not in routine
use. Today it is the layer between our workflows and the Leica Stellaris: the workflow speaks the
controller's commands, and the Stellaris driver turns them into actions on the microscope. The mock driver,
`zmart_controller.mock`, lets you try everything without a microscope.

## Author
Thom de Hoog, Center for Microscopy and Image Analysis (ZMB), University of
Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).

## License
MIT License. See LICENSE file for details.

## Links

- [ZMART Microscopy](https://github.com/thomdehoog/ZMART-microscopy): the main repository, with the workflows and the drivers
- [ZMART drivers](https://github.com/thomdehoog/ZMART-drivers): the drivers that plug into this controller, one per microscope
- [ZMART analysis](https://github.com/thomdehoog/ZMART-analysis): the analysis engine that runs between acquisitions
- [ZMART viewer](https://github.com/thomdehoog/ZMART-viewer): the viewer
- [Center for Microscopy and Image Analysis (ZMB)](https://www.zmb.uzh.ch), University of Zurich
