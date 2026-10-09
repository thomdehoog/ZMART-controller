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

<br>

## The Problem

When you want to implement an automated workflow on a microscope, you likely run into two problems:

1. **Available time on the microscope is often scarce.** 

2. **You want to share the workflow, but it only runs on your specific microscope.**

<br>

## The Solution

The ZMART controller sits between your workflow and the microscope and addresses these two problems:

1. **A universal interface.** Your workflow talks to the controller instead of to the microscope directly.
   Behind the controller you can plug in a simulated microscope, so you can build and test the whole
   workflow at your desk, and go to the microscope only once it works and when you have time for it.

2. **A common vocabulary.** A ZMART driver translates the specific language a microscope speaks into a
   short list of shared commands, so a workflow written once runs on every microscope that has a driver.

<p align="center">
  <img src="docs/zmart-controller-overview-2.png" width="100%" alt="Three microscopes, each with its own driver plugged in, connect through the ZMART Controller, one universal command vocabulary, to a script, an interface and an AI agent">
</p>

### A common vocabulary

Everything you can say to a microscope:

```python
from zmart_controller import mic

# 1) See which drivers are installed and how each connects, then connect to one
mic.get_instruments()
mic.connect(String)

# 2) Learn about the connected setup in more detail
mic.get_info()

# 3) Discover the motors, where you are in xyz space, and change the position
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

## Want to give it a try?

1. **[Using the ZMART-controller](docs/use_the_controller/README.md).** Every command, what it does, and what it answers.
2. **[How do I plug in a ZMART-driver](docs/plug_in_a_driver/README.md).** What a driver is, how to install it, and how to write one.

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
