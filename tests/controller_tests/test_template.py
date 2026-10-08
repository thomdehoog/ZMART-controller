"""Tests for the driver template: the plugin to copy, and the ZmartDriver class to fill in.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import zmart_controller
from zmart_controller import utils
from zmart_controller.template import zmart_controller_plugin as plugin
from zmart_controller.template.zmart_driver import ZmartDriver

README = Path(__file__).parents[2] / "docs" / "1_plug_in_a_driver" / "README.md"


class PretendDriver(ZmartDriver):
    """A ZmartDriver filled in for a microscope that lives in memory."""

    folder: Path  # set by the test before connecting

    def __init__(self, connection):
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.exposure_ms = 10.0

    def disconnect(self):
        pass

    def get_info(self):
        return str(self.folder), "A pretend microscope. +z points up."

    def get_actuators(self):
        return ["motor"], ["motor"], ["motor", "piezo"]

    def get_xyz(self, with_actuators):
        p = self.position
        return p["x"], p["y"], p["z"], "motor", "motor", "motor"

    def get_canvas(self):
        return -1050.0, 1050.0, -1050.0, 1050.0, -100.0, 100.0

    def set_xyz(self, x, y, z, with_actuators):
        self.position = {"x": x, "y": y, "z": z}
        return "motor", "motor", "motor"

    def get_state(self):
        return {"exposure_ms": self.exposure_ms}, {"objective": "10x"}

    def set_state(self, changeable):
        self.exposure_ms = changeable.get("exposure_ms", self.exposure_ms)
        return dict(changeable)

    def get_acquisition_settings(self):
        return {"format": {"options": ["json"], "active": "json"}}

    def acquire(self, position_label, acquisition_settings):
        path = self.folder / f"{position_label}.json"
        path.write_text(json.dumps({"position": self.position, "exposure_ms": self.exposure_ms}))
        p = self.position
        plane = {"path": str(path), "c": 0, "z": 0, "t": 0}
        plane.update(x_um=p["x"], y_um=p["y"], z_um=p["z"])
        return [str(path)], [plane]

    def get_procedures(self):
        return {"park": {"description": "Move the stage to its parking position."}}

    def run_procedure(self, procedure):
        if procedure["name"] != "park":
            raise ValueError(f"unknown procedure {procedure['name']!r}")


def test_the_plugin_offers_every_function():
    assert utils.driver_functions(plugin).keys() == {*utils.OPS, "disconnect"}


def test_an_unfilled_driver_says_what_is_missing():
    with pytest.raises(NotImplementedError, match="ZmartDriver.__init__"):
        zmart_controller.validate_driver(plugin)


def test_a_filled_in_driver_passes_validation_and_acquires(monkeypatch, tmp_path):
    PretendDriver.folder = tmp_path
    monkeypatch.setattr(plugin, "ZmartDriver", PretendDriver)
    assert zmart_controller.validate_driver(plugin) == []
    session = zmart_controller.set_instrument(plugin)
    try:
        session.set_xyz(100.0, 50.0, 0.0)
        answer = session.acquire(position_label="A1")
        assert zmart_controller.check_acquire_answer(answer) == []
        assert session.run_procedure({"name": "park"})["content"] == {"ran": "park"}
    finally:
        session.disconnect()


def test_every_method_the_plugin_calls_exists_on_the_class():
    called = set(re.findall(r"\bhandle\.(\w+)\(", Path(plugin.__file__).read_text()))
    assert called <= {name for name in dir(ZmartDriver) if not name.startswith("_")}


def test_the_readme_shows_the_shipped_plugin():
    """The code block in the Part 1 README is the template file itself, so they cannot drift."""
    text = README.read_text()
    block = text.split("```python\n# zmart_controller_plugin.py\n", 1)[1].split("```", 1)[0]
    source = Path(plugin.__file__).read_text().split('"""', 2)[2]
    assert block.strip("\n") == source.strip("\n")
