"""Where a microscope saves, what it still needs set up, and what each setting starts at.

``get_info`` answers three things: the microscope in words, the folder it
saves under (``output_root``, None while that is not set up), and its
set-up items, each done or not with what to do about it. Each acquisition
setting may say its ``default`` beside its ``active`` value.
"""

from __future__ import annotations

import pytest

from zmart_controller import ZmartController, validate_driver
from zmart_controller.template.zmart_driver import ZmartDriver


class Scope(ZmartDriver):
    """A driver that lives in memory; ``info`` and ``settings`` are what it answers."""

    info = ("A scope in memory. +z points up.", "D:/ZMART-data", {"limits": {"done": True, "says": "published"}})
    settings = {"format": {"options": ["ome-zarr", "ome-tiff"], "active": "ome-zarr", "default": "ome-zarr"}}

    def __init__(self, connection):
        pass

    def disconnect(self):
        pass

    def get_info(self):
        return True, self.info

    def get_actuators(self):
        return True, (["motor"], ["motor"], ["motor"])

    def get_xyz(self, with_actuators):
        return True, (0.0, 0.0, 0.0, {"x": {"motor": 0.0}, "y": {"motor": 0.0}, "z": {"motor": 0.0}},
                      (-10.0, 10.0, -10.0, 10.0, -1.0, 1.0))

    def get_state(self):
        return True, ({}, {})

    def get_acquisition_settings(self):
        return True, self.settings

    def get_procedures(self):
        return True, {}


def scope(**answers):
    return type("Answering", (Scope,), answers)


def test_get_info_says_where_it_saves_and_what_is_set_up():
    session = ZmartController(Scope, {})

    content = session.get_info()["content"]

    assert content == {
        "description": "A scope in memory. +z points up.",
        "output_root": "D:/ZMART-data",
        "setup": {"limits": {"done": True, "says": "published"}},
    }
    assert validate_driver(Scope, {}) == []


def test_a_scope_not_yet_told_where_to_save_says_so_and_how():
    driver = scope(info=(
        "A scope in memory. +z points up.",
        None,
        {"data_location": {"done": False, "says": "run set_data_location.ipynb once"}},
    ))

    content = ZmartController(driver, {}).get_info()["content"]

    assert content["output_root"] is None
    assert content["setup"]["data_location"] == {"done": False, "says": "run set_data_location.ipynb once"}
    assert validate_driver(driver, {}) == []


@pytest.mark.parametrize(
    ("info", "says"),
    [
        (("A scope. +z up.", 42, {}), "output_root"),
        (("A scope. +z up.", None, ["limits"]), "setup"),
        (("A scope. +z up.", None, {"limits": {"done": "yes", "says": "x"}}), "done"),
        (("A scope. +z up.", None, {"limits": {"done": False, "says": ""}}), "what to do"),
    ],
)
def test_a_wrong_answer_is_named(info, says):
    problems = validate_driver(scope(info=info), {})

    assert any(says in problem for problem in problems), problems


def test_a_default_may_differ_from_the_active_value():
    driver = scope(settings={
        "save_to": {"options": "a folder", "active": "E:/one-run", "default": "D:/ZMART-data"},
        "format": {"options": ["ome-zarr", "ome-tiff"], "active": "ome-tiff", "default": "ome-zarr"},
    })

    content = ZmartController(driver, {}).get_acquisition_settings()["content"]

    assert content["format"]["default"] == "ome-zarr"
    assert validate_driver(driver, {}) == []


def test_a_default_that_is_not_an_option_is_named():
    driver = scope(settings={"format": {"options": ["ome-zarr", "ome-tiff"], "active": "ome-zarr", "default": "png"}})

    problems = validate_driver(driver, {})

    assert any("default" in problem and "format" in problem for problem in problems), problems
