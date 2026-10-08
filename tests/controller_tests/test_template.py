"""Tests for the two-file driver: the template to copy, and the plugin inside the controller.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

import zmart_controller
from zmart_controller import plugin, utils
from zmart_controller.template.zmart_driver import ZmartDriver

README = Path(__file__).parents[2] / "docs" / "1_plug_in_a_driver" / "README.md"
TEMPLATE = Path(zmart_controller.template.__file__).parent


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


def test_the_template_loads_and_offers_every_function():
    driver = zmart_controller.load_driver(TEMPLATE)
    assert driver.NAME == "my-scope"
    assert driver.CONNECTION["host"] == "127.0.0.1"
    assert utils.driver_functions(driver).keys() == {*utils.OPS, "disconnect"}


def test_an_unfilled_driver_says_what_is_missing():
    with pytest.raises(NotImplementedError, match="ZmartDriver.__init__"):
        zmart_controller.validate_driver(zmart_controller.load_driver(TEMPLATE))


def test_a_filled_in_driver_passes_validation_and_acquires(tmp_path):
    PretendDriver.folder = tmp_path
    driver = plugin.functions_for(PretendDriver, "pretend", {})
    assert zmart_controller.validate_driver(driver) == []
    session = zmart_controller.set_instrument(driver)
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


def test_a_folder_missing_a_file_is_refused(tmp_path):
    shutil.copy(TEMPLATE / "zmart_driver.json", tmp_path)
    with pytest.raises(ValueError, match="zmart_driver.py is missing"):
        zmart_controller.load_driver(tmp_path)


def test_a_copied_template_is_installed_from_its_folder_or_json(tmp_path):
    folder = tmp_path / "my_scope"
    shutil.copytree(TEMPLATE, folder)
    settings = folder / "zmart_driver.json"
    settings.write_text(settings.read_text().replace('"my-scope"', '"my-scope-2"'))
    try:
        assert zmart_controller.register_driver(folder) == "my-scope-2"
        assert zmart_controller.register_driver(settings) == "my-scope-2"
        assert zmart_controller.get_drivers() == ["mock", "my-scope-2"]
        shown = zmart_controller.get_instruments()["my-scope-2"]
        assert shown["host"] == "127.0.0.1" and "password" not in shown
        with pytest.raises(NotImplementedError):  # it connects through the plugin
            zmart_controller.set_instrument("my-scope-2")
    finally:
        zmart_controller.remove_driver("my-scope-2")


def test_the_readme_quotes_the_controller_and_names_every_method():
    """Every controller function the README quotes is the code itself, so they cannot drift."""
    text = README.read_text()
    source = Path(plugin.__file__).read_text()
    quoted = re.findall(r"```python\n# zmart_controller/plugin.py\n\n(.*?)```", text, re.S)
    assert quoted
    for block in quoted:
        for function in block.strip("\n").split("\n\n\n"):
            indented = "\n".join("    " + line if line else line for line in function.splitlines())
            assert function in source or indented in source
    for name in dir(ZmartDriver):
        if not name.startswith("_"):
            assert f"def {name}(self" in text
