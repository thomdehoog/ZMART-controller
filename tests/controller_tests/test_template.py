"""Tests for the driver template: the plugin to copy, and the scope to fill in.

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
from zmart_controller.template import scope
from zmart_controller.template import zmart_controller_plugin as plugin

README = Path(__file__).parents[2] / "docs" / "1_plug_in_a_driver" / "README.md"


class PretendScope:
    """A scope.py filled in for a microscope that lives in memory."""

    def __init__(self, folder):
        self.folder = folder

    def connect(self, connection):
        return {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "exposure_ms": 10.0}

    def disconnect(self, handle):
        pass

    def get_info(self, handle):
        return str(self.folder), "A pretend microscope. +z points up."

    def get_actuators(self, handle):
        return ["motor"], ["motor"], ["motor", "piezo"]

    def get_xyz(self, handle, with_actuators):
        p = handle["position"]
        return p["x"], p["y"], p["z"], "motor", "motor", "motor"

    def get_canvas(self, handle):
        return -1050.0, 1050.0, -1050.0, 1050.0, -100.0, 100.0

    def set_xyz(self, handle, x, y, z, with_actuators):
        handle["position"] = {"x": x, "y": y, "z": z}
        return "motor", "motor", "motor"

    def get_state(self, handle):
        return {"exposure_ms": handle["exposure_ms"]}, {"objective": "10x"}

    def set_state(self, handle, changeable):
        handle.update(changeable)
        return dict(changeable)

    def get_acquisition_settings(self, handle):
        return {"format": {"options": ["json"], "active": "json"}}

    def acquire(self, handle, position_label, acquisition_settings):
        path = self.folder / f"{position_label}.json"
        path.write_text(json.dumps(handle))
        p = handle["position"]
        plane = {
            "path": str(path),
            "c": 0,
            "z": 0,
            "t": 0,
            "x_um": p["x"],
            "y_um": p["y"],
            "z_um": p["z"],
        }
        return [str(path)], [plane]

    def get_procedures(self, handle):
        return {"park": {"description": "Move the stage to its parking position."}}

    def run_procedure(self, handle, procedure):
        if procedure["name"] != "park":
            raise ValueError(f"unknown procedure {procedure['name']!r}")


def test_the_plugin_offers_every_function():
    assert utils.driver_functions(plugin).keys() == {*utils.OPS, "disconnect"}


def test_an_unfilled_scope_says_what_is_missing():
    with pytest.raises(NotImplementedError, match="scope.connect"):
        zmart_controller.validate_driver(plugin)


def test_a_filled_in_scope_passes_validation_and_acquires(monkeypatch, tmp_path):
    monkeypatch.setattr(plugin, "scope", PretendScope(tmp_path))
    assert zmart_controller.validate_driver(plugin) == []
    session = zmart_controller.set_instrument(plugin)
    try:
        session.set_xyz(100.0, 50.0, 0.0)
        answer = session.acquire(position_label="A1")
        assert zmart_controller.check_acquire_answer(answer) == []
        assert session.run_procedure({"name": "park"})["content"] == {"ran": "park"}
    finally:
        session.disconnect()


def test_every_scope_function_the_plugin_calls_exists():
    called = set(re.findall(r"\bscope\.(\w+)\(", Path(plugin.__file__).read_text()))
    assert called <= {name for name in dir(scope) if not name.startswith("_")}


def test_the_readme_shows_the_shipped_plugin():
    """The code block in the Part 1 README is the template file itself, so they cannot drift."""
    text = README.read_text()
    block = text.split("```python\n# zmart_controller_plugin.py\n", 1)[1].split("```", 1)[0]
    source = Path(plugin.__file__).read_text().split('"""', 2)[2]
    assert block.strip("\n") == source.strip("\n")
