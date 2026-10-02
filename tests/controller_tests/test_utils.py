"""Tests for the utilities: registering, finding and forgetting drivers.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from zmart_controller import utils, validate_driver

MOCK_FOLDER = Path(__file__).parents[1] / "mock_zmart_driver"


@pytest.fixture
def scratch_identity():
    """A throwaway identity, removed from the registry after the test."""
    connection = {"vendor": "test", "microscope": "scratch", "api": "t-api"}
    yield connection
    utils.REGISTRY.pop(utils._identity(connection), None)


def _full_ops():
    return {name: (lambda *a, **k: None) for name in utils.OPS}


class TestRegister:
    def test_missing_ops_raise(self, scratch_identity):
        with pytest.raises(ValueError, match="missing ops"):
            utils.register(scratch_identity, ops={"connect": lambda c: None})

    def test_missing_identity_keys_raise_without_values(self):
        # the error must list key names only -- connection dicts may carry credentials
        with pytest.raises(ValueError) as err:
            utils.register({"vendor": "test", "password": "hunter2"}, ops=_full_ops())
        assert "microscope" in str(err.value)
        assert "hunter2" not in str(err.value)

    def test_duplicate_identity_overwrites_with_warning(self, scratch_identity, caplog):
        utils.register(scratch_identity, ops=_full_ops())
        with caplog.at_level("WARNING"):
            utils.register(scratch_identity, ops=_full_ops())
        assert "already registered" in caplog.text

    def test_connection_dict_is_copied(self, scratch_identity):
        utils.register(scratch_identity, ops=_full_ops())
        scratch_identity["client"] = "mutated-later"
        stored = next(i for i in utils.get_instruments() if i["microscope"] == "scratch")
        assert "client" not in stored


class TestGetInstruments:
    def test_returns_copies(self):
        first = utils.get_instruments()[0]
        first["vendor"] = "vandalized"
        assert utils.get_instruments()[0]["vendor"] != "vandalized"

    def test_sorted_by_identity(self, scratch_identity):
        utils.register(scratch_identity, ops=_full_ops())
        vendors = [i["vendor"] for i in utils.get_instruments()]
        assert vendors == sorted(vendors)

    def test_mock_is_registered(self):
        assert any(i["vendor"] == "mock" for i in utils.get_instruments())


class TestDiscovery:
    def test_installed_driver_is_found_without_an_import(self, monkeypatch):
        # Pretend a package is installed that announces the mock as a driver.
        from importlib.metadata import EntryPoint

        fake = EntryPoint("fake", "mock_zmart_driver", utils.ENTRY_POINT_GROUP)
        monkeypatch.setattr(
            utils,
            "entry_points",
            lambda group: [fake] if group == utils.ENTRY_POINT_GROUP else [],
        )
        monkeypatch.setattr(utils, "_discovered", False)
        utils.REGISTRY.pop(("mock", "mock-scope", "mock-api"), None)

        assert any(i["vendor"] == "mock" for i in utils.get_instruments())

    def test_a_broken_driver_does_not_hide_the_others(self, monkeypatch, caplog):
        from importlib.metadata import EntryPoint

        broken = EntryPoint("broken", "no_such_package_xyz", utils.ENTRY_POINT_GROUP)
        monkeypatch.setattr(utils, "entry_points", lambda group: [broken])
        monkeypatch.setattr(utils, "_discovered", False)
        with caplog.at_level("ERROR"):
            utils.get_instruments()  # must not raise
        assert "broken" in caplog.text


FUNCTIONS = """
from mock_zmart_driver.zmart_controller import (
    connect, disconnect, get_info, get_actuators, get_xyz, set_xyz, get_state,
    set_state, get_acquisition_options, acquire, get_procedures, run_procedure,
)
"""


def make_driver(root, microscope, *, functions=FUNCTIONS, manifest=None, plugin=True):
    """Write a driver folder: zmart_controller/zmart.json + __init__.py with the mock's functions."""
    folder = root / "zmart_controller" if plugin else root
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").write_text(functions)
    if manifest is None:
        manifest = {
            "contract": 1,
            "instruments": [{"vendor": "acme", "microscope": microscope, "api": "acme-sdk"}],
        }
    (folder / "zmart.json").write_text(
        manifest if isinstance(manifest, str) else json.dumps(manifest)
    )
    return root


@pytest.fixture
def forget_acme():
    yield
    for key in [k for k in utils.REGISTRY if k[0] == "acme"]:
        utils.REGISTRY.pop(key)


class TestRegisterDriver:
    def test_from_a_driver_folder(self, tmp_path, forget_acme):
        driver = make_driver(tmp_path / "acme", "from-folder")
        added = utils.register_driver(driver)
        assert [i["microscope"] for i in added] == ["from-folder"]
        assert any(i["microscope"] == "from-folder" for i in utils.get_instruments())

    def test_manifest_directly_in_the_folder(self, tmp_path, forget_acme):
        driver = make_driver(tmp_path / "acme", "flat", plugin=False)
        assert [i["microscope"] for i in utils.register_driver(driver)] == ["flat"]

    def test_from_a_module_name(self):
        utils.REGISTRY.pop(("mock", "mock-scope", "mock-api"), None)
        added = utils.register_driver("mock_zmart_driver", remember=False)
        assert [i["vendor"] for i in added] == ["mock"]

    def test_calling_it_twice_is_harmless(self, tmp_path, forget_acme):
        driver = make_driver(tmp_path / "acme", "twice")
        utils.register_driver(driver)
        utils.register_driver(driver)
        assert sum(i["microscope"] == "twice" for i in utils.get_instruments()) == 1

    def test_two_drivers_both_called_zmart_controller_load_side_by_side(
        self, tmp_path, forget_acme
    ):
        first = make_driver(tmp_path / "first", "scope-1")
        second = make_driver(tmp_path / "second", "scope-2")
        utils.register_driver(first)
        utils.register_driver(second)
        names = {i["microscope"] for i in utils.get_instruments() if i["vendor"] == "acme"}
        assert names == {"scope-1", "scope-2"}

    def test_several_instruments_in_one_driver(self, tmp_path, forget_acme):
        manifest = {
            "contract": 1,
            "instruments": [
                {"vendor": "acme", "microscope": "left", "api": "acme-sdk"},
                {"vendor": "acme", "microscope": "right", "api": "acme-sdk", "host": "10.0.0.2"},
            ],
        }
        driver = make_driver(tmp_path / "acme", "", manifest=manifest)
        added = utils.register_driver(driver)
        assert [i["microscope"] for i in added] == ["left", "right"]
        assert added[1]["host"] == "10.0.0.2"

    def test_the_setup_guide_works_on_the_mock(self):
        utils.REGISTRY.pop(("mock", "mock-scope", "mock-api"), None)
        added = utils.register_driver("mock_zmart_driver", remember=False)
        assert [i["vendor"] for i in added] == ["mock"]
        assert utils.remembered_drivers() == []


class TestRegisterDriverRefusals:
    def test_nothing_there(self, tmp_path):
        with pytest.raises(ValueError, match="no driver found"):
            utils.register_driver("acme_does_not_exist_anywhere")
        (tmp_path / "empty").mkdir()
        with pytest.raises(ValueError, match="no zmart_controller/zmart.json"):
            utils.register_driver(tmp_path / "empty")

    def test_a_missing_function_is_named(self, tmp_path):
        functions = FUNCTIONS.replace("get_xyz, ", "")
        driver = make_driver(tmp_path / "acme", "incomplete", functions=functions)
        with pytest.raises(ValueError, match=r"missing these functions: \['get_xyz'\]"):
            utils.register_driver(driver)

    def test_unknown_contract_version(self, tmp_path):
        manifest = {"contract": 99, "instruments": [{"vendor": "a", "microscope": "b", "api": "c"}]}
        driver = make_driver(tmp_path / "acme", "", manifest=manifest)
        with pytest.raises(ValueError, match='"contract": 1'):
            utils.register_driver(driver)

    def test_no_instruments(self, tmp_path):
        driver = make_driver(tmp_path / "acme", "", manifest={"contract": 1, "instruments": []})
        with pytest.raises(ValueError, match="at least one instrument"):
            utils.register_driver(driver)

    def test_instrument_missing_identity(self, tmp_path):
        manifest = {"contract": 1, "instruments": [{"vendor": "acme", "password": "hunter2"}]}
        driver = make_driver(tmp_path / "acme", "", manifest=manifest)
        with pytest.raises(ValueError) as err:
            utils.register_driver(driver)
        assert "microscope" in str(err.value) and "hunter2" not in str(err.value)

    def test_broken_json(self, tmp_path):
        driver = make_driver(tmp_path / "acme", "", manifest="{not json")
        with pytest.raises(ValueError, match="not valid JSON"):
            utils.register_driver(driver)

    def test_nothing_is_registered_when_a_function_is_missing(self, tmp_path):
        functions = FUNCTIONS.replace("acquire, ", "")
        driver = make_driver(tmp_path / "acme", "half", functions=functions)
        with pytest.raises(ValueError):
            utils.register_driver(driver)
        assert not any(i["vendor"] == "acme" for i in utils.get_instruments())


class TestNestedSettingsAreCopied:
    def test_editing_a_listed_instrument_changes_nothing_stored(self, scratch_identity):
        given = dict(scratch_identity, origin={"x": 0.0, "y": 0.0, "z": 0.0})
        utils.register(given, ops=_full_ops())

        listed = next(i for i in utils.get_instruments() if i["microscope"] == "scratch")
        listed["origin"]["x"] = 500.0

        again = next(i for i in utils.get_instruments() if i["microscope"] == "scratch")
        assert again["origin"]["x"] == 0.0
        assert given["origin"]["x"] == 0.0

    def test_editing_the_input_later_changes_nothing_stored(self, scratch_identity):
        given = dict(scratch_identity, origin={"x": 0.0})
        utils.register(given, ops=_full_ops())
        given["origin"]["x"] = 500.0
        stored = next(i for i in utils.get_instruments() if i["microscope"] == "scratch")
        assert stored["origin"]["x"] == 0.0


class TestRememberedDrivers:
    def test_a_registered_driver_is_remembered_and_plugged_in_next_session(
        self, tmp_path, forget_acme, monkeypatch
    ):
        driver = make_driver(tmp_path / "acme", "kept")
        utils.register_driver(driver)
        assert utils.remembered_drivers() == [str(driver.resolve())]

        # A new session: nothing registered, nothing discovered yet.
        utils.REGISTRY.pop(("acme", "kept", "acme-sdk"))
        monkeypatch.setattr(utils, "_discovered", False)
        assert any(i["microscope"] == "kept" for i in utils.get_instruments())

    def test_remember_false_leaves_no_trace(self, tmp_path, forget_acme):
        utils.register_driver(make_driver(tmp_path / "acme", "once"), remember=False)
        assert utils.remembered_drivers() == []

    def test_forget_driver(self, tmp_path, forget_acme):
        driver = make_driver(tmp_path / "acme", "forgot")
        utils.register_driver(driver)
        assert utils.forget_driver(driver) is True
        assert utils.remembered_drivers() == []
        assert utils.forget_driver(driver) is False

    def test_a_remembered_driver_that_vanished_is_skipped(self, monkeypatch, caplog):
        utils._save_remembered(["/no/such/place/acme_gone_driver"])
        monkeypatch.setattr(utils, "_discovered", False)
        with caplog.at_level("ERROR"):
            utils.get_instruments()  # must not raise
        assert "acme_gone_driver" in caplog.text


def make_driver_package(root, name, microscope):
    """Write a driver laid out like the mock: a package whose functions import its own modules.

    ``root/name/`` is the package, with a module of its own (``vendor.py``) and a
    ``zmart_controller/`` folder that reaches it by the full name ``name.vendor``,
    as docs/driver.md asks of driver authors.
    """
    package = root / name
    plugin = package / "zmart_controller"
    plugin.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "vendor.py").write_text(f"MICROSCOPE = {microscope!r}\n")
    (plugin / "__init__.py").write_text(f"from {name}.vendor import MICROSCOPE\n" + FUNCTIONS)
    manifest = {
        "contract": 1,
        "instruments": [{"vendor": "acme", "microscope": microscope, "api": "acme-sdk"}],
    }
    (plugin / "zmart.json").write_text(json.dumps(manifest))
    return package


@pytest.fixture
def unimport():
    """Forget the driver packages a test imported, as a new Python session would."""
    names = []
    yield names
    for module in [m for m in sys.modules if m.split(".")[0] in names]:
        del sys.modules[module]


class TestDriverPackages:
    def test_a_package_folder_registers_although_its_parent_is_not_importable(
        self, tmp_path, forget_acme, unimport
    ):
        name = f"acme_pkg_{tmp_path.name}".replace("-", "_")
        unimport.append(name)
        package = make_driver_package(tmp_path / "drivers", name, "packaged")
        added = utils.register_driver(package, remember=False)
        assert [i["microscope"] for i in added] == ["packaged"]
        assert sys.modules[f"{name}.vendor"].MICROSCOPE == "packaged"

    def test_the_mock_registers_by_its_folder(self):
        utils.REGISTRY.pop(("mock", "mock-scope", "mock-api"), None)
        added = utils.register_driver(MOCK_FOLDER, remember=False)
        assert [i["vendor"] for i in added] == ["mock"]

    def test_a_driver_given_by_name_is_remembered_by_its_folder_and_found_next_session(
        self, tmp_path, forget_acme, unimport, monkeypatch
    ):
        name = f"acme_pkg_{tmp_path.name}".replace("-", "_")
        unimport.append(name)
        package = make_driver_package(tmp_path / "drivers", name, "by-name")
        monkeypatch.syspath_prepend(str(tmp_path / "drivers"))
        utils.register_driver(name)
        assert utils.remembered_drivers() == [str(package.resolve())]

        # A new session started elsewhere: the driver's folder is no longer importable.
        monkeypatch.undo()
        monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(tmp_path / "config"))
        for module in [m for m in sys.modules if m.split(".")[0] == name]:
            del sys.modules[module]
        utils.REGISTRY.pop(("acme", "by-name", "acme-sdk"))
        monkeypatch.setattr(utils, "_discovered", False)
        assert any(i["microscope"] == "by-name" for i in utils.get_instruments())

    def test_forgetting_by_name_matches_remembering_by_name(
        self, tmp_path, forget_acme, unimport, monkeypatch
    ):
        name = f"acme_pkg_{tmp_path.name}".replace("-", "_")
        unimport.append(name)
        make_driver_package(tmp_path / "drivers", name, "forget-me")
        monkeypatch.syspath_prepend(str(tmp_path / "drivers"))
        utils.register_driver(name)
        assert utils.forget_driver(name) is True
        assert utils.remembered_drivers() == []

    def test_a_different_package_of_the_same_name_is_refused_by_name(
        self, tmp_path, forget_acme, unimport
    ):
        name = f"acme_pkg_{tmp_path.name}".replace("-", "_")
        unimport.append(name)
        first = make_driver_package(tmp_path / "one", name, "first")
        second = make_driver_package(tmp_path / "two", name, "second")
        utils.register_driver(first, remember=False)
        with pytest.raises(ValueError, match=f"another package named {name}"):
            utils.register_driver(second, remember=False)


class TestConfigRoot:
    def test_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(tmp_path))
        assert utils.config_root() == tmp_path

    def test_per_os_default(self, monkeypatch):
        monkeypatch.delenv("ZMART_MICROSCOPY_ROOT", raising=False)
        monkeypatch.setattr(utils.platform, "system", lambda: "Windows")
        monkeypatch.setenv("PROGRAMDATA", r"C:\\ProgramData")
        assert str(utils.config_root()).endswith("zmart-microscopy")
        monkeypatch.setattr(utils.platform, "system", lambda: "Darwin")
        assert utils.config_root() == utils.Path(
            "/Library/Application Support/zmart-microscopy"
        )
        monkeypatch.setattr(utils.platform, "system", lambda: "Linux")
        assert utils.config_root() == utils.Path("/etc/zmart-microscopy")


# ---- validate_driver: does a driver fit the contract?

MOCK = ("mock", "mock-scope", "mock-api")


def _mock_instrument():
    return {"vendor": "mock", "microscope": "mock-scope", "api": "mock-api"}


def _break(monkeypatch, name, func):
    """Swap one of the mock's functions in the table the registry uses."""
    monkeypatch.setitem(utils.REGISTRY[MOCK]["ops"], name, func)


def test_the_mock_fits():
    assert validate_driver(_mock_instrument()) == []


def test_problems_are_named(monkeypatch):
    # Break two answers and expect plain sentences about those two, nothing else.
    _break(monkeypatch, "get_xyz", lambda handle, **kw: {"success": True, "report": {"x": {}}})
    _break(monkeypatch, "get_info", lambda handle: {"success": True, "report": {}})
    problems = validate_driver(_mock_instrument())
    assert "get_info: the report must contain output_root" in problems
    assert any(p.startswith("get_xyz: axis 'x' is missing") for p in problems)
    assert any(p.startswith("get_xyz: axis 'y' is missing") for p in problems)
    assert not any(p.startswith("get_state") for p in problems)


def test_a_driver_without_a_description_still_fits(monkeypatch):
    """The description is for whoever drives the microscope; the controller runs without it."""
    _break(monkeypatch, "get_info", lambda handle: {"success": True, "report": {"output_root": "x"}})
    assert validate_driver(_mock_instrument()) == []


@pytest.mark.parametrize("description", ["", "   ", 42, ["a microscope"]])
def test_a_description_that_says_nothing_is_reported(monkeypatch, description):
    _break(
        monkeypatch,
        "get_info",
        lambda handle: {"success": True, "report": {"output_root": "x", "description": description}},
    )
    assert validate_driver(_mock_instrument()) == [
        "get_info: description must be text that describes the microscope"
    ]


def test_the_mock_describes_itself():
    from zmart_controller import set_instrument

    session = set_instrument(_mock_instrument())
    try:
        description = session.get_info()["report"]["description"]
    finally:
        session.disconnect()
    assert isinstance(description, str) and len(description) > 200
    for word in ("stage", "objective", "exposure", "laser"):
        assert word in description.lower(), word


def test_a_bare_answer_without_the_envelope_is_reported(monkeypatch):
    _break(monkeypatch, "get_procedures", lambda handle: {"autofocus": {}})
    problems = validate_driver(_mock_instrument())
    assert any('get_procedures must return {"success"' in p for p in problems)


@pytest.fixture(autouse=True)
def _mock_present():
    if MOCK not in utils.REGISTRY:
        utils.register_driver("mock_zmart_driver", remember=False)
