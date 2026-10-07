# ZMART Controller

[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](pyproject.toml)
[![tests](https://img.shields.io/badge/tests-pytest-blue)](#testing)
[![status](https://img.shields.io/badge/status-early%20use-orange)](#status)

<table>
<tr>
<td width="170"><img src="docs/zmart-controller-icon.png" width="150" alt="ZMART Controller"></td>
<td valign="middle">

The **ZMART Controller** provides a small, universal schema for driving a microscope from Python. Writing your automated workflow with its commands simplifies implementing, testing and simulating workflows. On top of this, when you build your workflow with this vocabulary, it runs on any microscope that has a ZMART driver for it. It is part of [**ZMART**](https://github.com/thomdehoog/ZMART-microscopy) (ZMB's Microscopy-Agnostic Research Toolkit), the tools we are building for smart microscopy at the Center for Microscopy and Image Analysis (ZMB), University of Zurich.

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

Note: we are aware of the [useq-schema](https://github.com/pymmcore-plus/useq-schema) from the Micro-Manager community and of Anthropic's [Model Hardware Standard](https://www.anthropic.com/news/model-hardware-standard-research-preview). We might switch, because both have real upsides, but currently the useq-schema is not interoperable enough for our needs and the Model Hardware Standard is not released to the public yet.
<p align="center">
  <img src="docs/zmart-controller-overview-2.png" width="100%" alt="Three microscopes, each with its own driver plugged in, connect through the ZMART Controller, one universal command vocabulary, to a script, an interface and an AI agent">
</p>

### The vocabulary

Everything you can say to a microscope:

```python
import zmart_controller

# 1) Plug in a driver and connect to its microscope
zmart_controller.set_instrument(driver, connection=Dict)

# 2) Learn about the connected setup: where images go, and the microscope in plain words
zmart_controller.get_info()

# 3) Discover the motors, then read the position and travel range, or move (micrometers)
zmart_controller.get_actuators()
zmart_controller.get_xyz()
zmart_controller.set_xyz(x, y, z, with_actuators=Dict)

# 4) Capture the instrument settings, and apply them again later
zmart_controller.get_state()
zmart_controller.set_state(Dict)

# 5) Capture and save an image with the current settings and position
zmart_controller.get_acquisition_settings()
zmart_controller.acquire(position_label=String, acquisition_settings=Dict)

# 6) Run a routine the microscope offers (for example autofocus)
zmart_controller.get_procedures()
zmart_controller.run_procedure(Dict)

# 7) Close the connection
zmart_controller.disconnect()
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


## The three parts

The documentation follows the three steps of using the controller. Each part has a README, which is
its complete documentation, and a tutorial, which walks you through it step by step.

1. **[Plug in a driver](docs/1_plug_in_a_driver/README.md).** What a driver is, what it must provide, where its functions go, and how to
   plug it in. → [tutorial](docs/1_plug_in_a_driver/tutorial.md)
2. **[Use the controller](docs/2_use_the_controller/README.md).** Every command, what it does, and what it answers.
   → [tutorial](docs/2_use_the_controller/tutorial.md)
3. **[Build your workflow](docs/3_build_your_workflow/README.md).** Put the commands together into an automated workflow, build it on the
   mock driver, and run it on a real microscope.
   → [tutorial](docs/3_build_your_workflow/tutorial.md)

## Status

This is version 0.1. We do not use it daily yet, because our smart-microscopy workflows are not in routine
use. Today it is the layer between our workflows and the Leica Stellaris: the workflow speaks the
controller's commands, and the Stellaris driver turns them into actions on the microscope. The mock driver,
`zmart_controller.mock`, lets you try everything without a microscope.

## Testing

The tests run on the mock driver, so they need no microscope. From a clone of this repository:

```bash
pip install -e ".[test]"
python -m pytest
```

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
