"""Tests for the utilities: the configuration folder, and checking a driver against the contract.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import zmart_controller.mock as mock
from zmart_controller import check_acquire_answer, registry, validate_driver


class TestConfigRoot:
    def test_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(tmp_path))
        assert registry.config_root() == tmp_path

    def test_per_os_default(self, monkeypatch):
        monkeypatch.delenv("ZMART_MICROSCOPY_ROOT", raising=False)
        monkeypatch.setattr(registry.platform, "system", lambda: "Windows")
        monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
        assert str(registry.config_root()).endswith("zmart-microscopy")
        monkeypatch.setattr(registry.platform, "system", lambda: "Darwin")
        assert registry.config_root() == registry.Path(
            "/Library/Application Support/zmart-microscopy"
        )
        monkeypatch.setattr(registry.platform, "system", lambda: "Linux")
        assert registry.config_root() == registry.Path("/etc/zmart-microscopy")


# ---- validate_driver: does a driver fit the contract?


def _break(monkeypatch, name, func):
    """Swap one of the mock driver's functions for a broken one, for this test only."""
    monkeypatch.setattr(mock, name, func)


def test_the_mock_fits():
    assert validate_driver(mock) == []


def test_problems_are_named(monkeypatch):
    # Break two answers and expect plain sentences about those two, nothing else.
    _break(monkeypatch, "get_xyz", lambda handle, **kw: {"success": True, "content": {"x": {}}})
    _break(monkeypatch, "get_info", lambda handle: {"success": True, "content": {}})
    problems = validate_driver(mock)
    assert any(p.startswith("get_info: the content must contain description") for p in problems)
    assert any(p.startswith("get_xyz: axis 'x' is missing") for p in problems)
    assert any(p.startswith("get_xyz: axis 'y' is missing") for p in problems)
    assert not any(p.startswith("get_state") for p in problems)


def _xyz_with(**canvas_per_axis):
    """A get_xyz with the canvas given per axis.

    An axis left out of ``canvas_per_axis`` reports a canvas of [-150, 150].
    The value ``"absent"`` leaves the key out altogether.
    """

    def get_xyz(handle, **kw):
        content = {}
        for axis in ("x", "y", "z"):
            reading = {"value": 0.0, "actuator": "motoric"}
            canvas = canvas_per_axis.get(axis, [-150.0, 150.0])
            if canvas != "absent":
                reading["canvas"] = canvas
            content[axis] = reading
        return {"success": True, "content": content}

    return get_xyz


def test_a_driver_without_canvas_is_told_so(monkeypatch):
    _break(monkeypatch, "get_xyz", _xyz_with(z="absent"))
    assert validate_driver(mock) == ["get_xyz: axis 'z' is missing 'canvas'"]


@pytest.mark.parametrize(
    "canvas", [[-150.0], "far", [-150.0, "far"], [True, 150.0], [150.0, -150.0]]
)
def test_a_canvas_that_is_not_min_then_max_is_reported(monkeypatch, canvas):
    _break(monkeypatch, "get_xyz", _xyz_with(x=canvas))
    assert validate_driver(mock) == [
        "get_xyz: axis 'x' canvas must be [min, max] in micrometres, with min no larger than max"
    ]


@pytest.mark.parametrize("description", ["", "   ", 42, ["a microscope"]])
def test_a_description_that_says_nothing_is_reported(monkeypatch, description):
    _break(
        monkeypatch,
        "get_info",
        lambda handle: {
            "success": True,
            "content": {"description": description},
        },
    )
    assert validate_driver(mock) == [
        "get_info: the content must contain description, text that describes the microscope"
    ]


def test_the_mock_describes_itself():
    from zmart_controller import ZmartController

    session = ZmartController(mock)
    try:
        description = session.get_info()["content"]["description"]
    finally:
        session.disconnect()
    assert isinstance(description, str) and len(description) > 200
    for word in ("stage", "objective", "exposure", "laser"):
        assert word in description.lower(), word
    # The bounds are this microscope's configured limits, not the software's widest ones.
    for bounds in ("0 to 50", "0 to 800", "0.1 to 1000"):
        assert bounds in description, bounds


def test_a_bare_answer_without_the_envelope_is_reported(monkeypatch):
    _break(monkeypatch, "get_procedures", lambda handle: {"autofocus": {}})
    problems = validate_driver(mock)
    assert any('get_procedures must return {"success"' in p for p in problems)


# ---- check_acquire_answer: does an acquisition say where its files are?


def _acquire(**options):
    """Acquire once on the mock and return its answer, as a driver's own test would."""
    from zmart_controller import ZmartController

    session = ZmartController(mock)
    try:
        return session.acquire(position_label="A1", acquisition_settings=options or None)
    finally:
        session.disconnect()


def _answer(**content):
    base = {"position_label": "A1"}
    return {"success": True, "content": {**base, **content}}


def _plane(path, **entries):
    """One plane entry as the contract describes it, with any entry replaced."""
    return {
        "path": str(path),
        "c": 0,
        "z": 0,
        "t": 0,
        "x_um": 100.0,
        "y_um": 50.0,
        "z_um": 3.0,
        **entries,
    }


@pytest.fixture
def saved(tmp_path):
    """One saved image file, as an acquisition leaves it."""
    path = tmp_path / "A1.ome.tif"
    path.write_bytes(b"")
    return path


def test_the_mocks_acquisition_fits():
    assert check_acquire_answer(_acquire()) == []


def test_files_names_everything_the_acquisition_saved():
    content = _acquire(z_planes=2)["content"]
    names = [Path(path).name for path in content["files"]]
    assert names == ["A1_z000.ome.tif", "A1_z001.ome.tif", "A1.commands.json"]
    assert content["command_log"] in content["files"]


def test_an_ome_zarr_folder_counts_as_a_saved_file():
    assert check_acquire_answer(_acquire(format="ome-zarr")) == []


def test_an_answer_without_files_is_reported():
    problems = check_acquire_answer(_answer(images=["a.tif"]))
    assert problems == [
        "acquire: the content must contain files, the list of paths of every file it saved"
    ]


def test_a_file_that_is_not_there_is_reported(tmp_path, saved):
    problems = check_acquire_answer(
        _answer(files=[str(saved), str(tmp_path / "gone.tif")], planes=[_plane(saved)])
    )
    assert problems == [f"acquire: files names {tmp_path / 'gone.tif'}, which does not exist"]


def test_files_must_be_a_list_of_paths():
    assert check_acquire_answer(_answer(files="A1.ome.tif")) == [
        "acquire: files must be a list of paths, one per saved file"
    ]


def test_a_successful_acquisition_must_name_at_least_one_file():
    assert check_acquire_answer(_answer(files=[], planes=[])) == [
        "acquire: a successful acquisition must list at least one file in files",
        "acquire: a successful acquisition must describe at least one image plane in planes",
    ]


def test_a_failed_acquisition_may_list_no_files():
    answer = _answer(files=[], planes=[], reason="the image never arrived")
    answer["success"] = False
    assert check_acquire_answer(answer) == []


# ---- planes: which channel, depth and stage position each saved image is


def test_the_mock_describes_every_plane_of_a_stack():
    answer = _acquire(z_planes=3, z_step_um=2.0)
    assert check_acquire_answer(answer) == []
    content = answer["content"]
    bottom = content["position"]["z"]
    assert [(plane["z"], plane["z_um"]) for plane in content["planes"]] == [
        (0, bottom),
        (1, bottom + 2.0),
        (2, bottom + 4.0),
    ]
    assert {(plane["x_um"], plane["y_um"]) for plane in content["planes"]} == {
        (content["position"]["x"], content["position"]["y"])
    }


def test_an_answer_without_planes_is_reported(saved):
    assert check_acquire_answer(_answer(files=[str(saved)])) == [
        "acquire: the content must contain planes, one entry per saved image saying which "
        "file, channel, depth and stage position it is"
    ]


def test_planes_must_be_a_list_of_entries(saved):
    assert check_acquire_answer(_answer(files=[str(saved)], planes=3)) == [
        "acquire: planes must be a list with one dictionary per saved image plane"
    ]


def test_a_plane_missing_an_entry_is_reported(saved):
    plane = _plane(saved)
    del plane["z_um"], plane["c"]
    assert check_acquire_answer(_answer(files=[str(saved)], planes=[plane])) == [
        "acquire: planes[0] must contain c, z_um"
    ]


def test_a_plane_must_name_one_of_the_saved_files(tmp_path, saved):
    elsewhere = tmp_path / "B1.ome.tif"
    problems = check_acquire_answer(_answer(files=[str(saved)], planes=[_plane(elsewhere)]))
    assert problems == [f"acquire: planes[0] names {elsewhere}, which is not in files"]


@pytest.mark.parametrize("key, value", [("c", -1), ("z", 1.5), ("t", True), ("c", "GFP")])
def test_channel_depth_and_time_are_counted_from_zero(saved, key, value):
    problems = check_acquire_answer(
        _answer(files=[str(saved)], planes=[_plane(saved, **{key: value})])
    )
    assert problems == [f"acquire: planes[0] {key} must be a whole number from 0, got {value!r}"]


@pytest.mark.parametrize("key, value", [("x_um", "12"), ("z_um", float("nan")), ("y_um", False)])
def test_a_position_must_be_a_number_of_micrometres(saved, key, value):
    problems = check_acquire_answer(
        _answer(files=[str(saved)], planes=[_plane(saved, **{key: value})])
    )
    assert problems == [
        f"acquire: planes[0] {key} must be a number of micrometres, or None when unknown, "
        f"got {value!r}"
    ]


def test_a_position_the_driver_cannot_know_may_be_none(saved):
    plane = _plane(saved, x_um=None, y_um=None, z_um=None)
    assert check_acquire_answer(_answer(files=[str(saved)], planes=[plane])) == []


def test_a_driver_may_add_its_own_entries_to_a_plane(saved):
    plane = _plane(saved, channel_name="GFP", exposure_ms=20)
    assert check_acquire_answer(_answer(files=[str(saved)], planes=[plane])) == []


def test_two_planes_in_the_same_place_are_reported(saved):
    planes = [_plane(saved), _plane(saved, z_um=4.0)]
    assert check_acquire_answer(_answer(files=[str(saved)], planes=planes)) == [
        "acquire: planes[1] repeats channel 0, depth 0 and time 0 of an earlier plane"
    ]


def test_the_label_must_come_back():
    content = {"files": [], "planes": []}
    problems = check_acquire_answer({"success": False, "content": content})
    assert problems == [
        "acquire: the content must contain position_label",
    ]


def test_an_acquisition_without_the_envelope_is_reported():
    problems = check_acquire_answer({"files": []})
    assert problems == ['acquire must return {"success": ..., "content": ...}, got dict']


# ---- the drivers installed on this computer


def test_get_instruments_shows_each_connection_without_its_secrets(tmp_path):
    (tmp_path / "zmart_driver.py").write_text("from zmart_controller.mock import *  # noqa\n")
    (tmp_path / "zmart_driver.json").write_text(
        json.dumps(
            {
                "name": "pretend",
                "connection": {
                    "microscope": "pretend-01",
                    "api_type": "socket",
                    "host": "127.0.0.1",
                    "password": "hunter2",
                    "config": "C:/pretend/config.ini",
                },
            }
        )
    )
    registry.register_driver(tmp_path)
    try:
        assert registry.get_instruments() == {
            "mock": {},
            "pretend": {
                "microscope": "pretend-01",
                "api_type": "socket",
                "host": "127.0.0.1",
                "config": "C:/pretend/config.ini",
            },
        }
    finally:
        registry.remove_driver("pretend")
