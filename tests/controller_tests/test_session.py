"""Tests for the cross-vendor controller against the mock driver.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import zmart_controller.mock as mock
from zmart_controller import set_instrument


@pytest.fixture
def mic():
    session = set_instrument(mock)
    yield session
    session.disconnect()


class TestSetInstrument:
    def test_context_names_the_driver(self, mic):
        assert mic.context == {"driver": "zmart_controller.mock"}

    def test_connection_reaches_driver(self):
        # the connection dict is forwarded untouched to the driver's connect()
        session = set_instrument(mock, {"client": "my-client"})
        try:
            assert session.get_info()["content"]["client"] == "my-client"
        finally:
            session.disconnect()

    def test_a_driver_can_be_a_dict_of_functions(self):
        functions = {name: getattr(mock, name) for name in mock.__all__}
        session = set_instrument(functions)
        try:
            assert session.get_xyz()["success"] is True
        finally:
            session.disconnect()

    def test_a_missing_function_is_named(self):
        functions = {name: getattr(mock, name) for name in mock.__all__ if name != "set_xyz"}
        with pytest.raises(ValueError, match="set_xyz"):
            set_instrument(functions)

    def test_the_mock_is_reachable_from_the_package(self):
        import zmart_controller

        assert zmart_controller.mock is mock


class TestPosition:
    def test_set_get_roundtrip(self, mic):
        rec = mic.set_xyz(10, 20, 5)
        assert rec["success"] is True
        assert rec["content"]["position"] == {"x": 10, "y": 20, "z": 5}
        assert rec["content"]["actuators"]["z"] == "motoric"
        pos = mic.get_xyz()["content"]
        assert (pos["x"]["value"], pos["y"]["value"], pos["z"]["value"]) == (10, 20, 5)

    def test_origin_is_driver_configuration(self):
        # The origin is saved by the driver's own setup step and loaded at
        # connect, never set through the controller.
        from zmart_controller.mock.configuration import save
        from zmart_controller.session import set_instrument as open_session

        save("origin", {"x": 50_100.0, "y": 37_500.0, "z": 5_000.0})
        session = open_session(mock)
        try:
            assert not hasattr(session, "set_origin")
            session.set_xyz(10, 0, 0)
            assert session.get_xyz()["content"]["x"]["value"] == 10
            stage = session._handle.scope.send("GetStagePosition")["result"]
            assert stage["x"] == 50_110.0  # raw stage position = saved origin + user position
        finally:
            session.disconnect()

    def test_get_actuators_lists_options(self, mic):
        assert mic.get_actuators()["content"]["z"] == ["motoric", "piezo"]

    def test_actuator_selector_reported_back(self, mic):
        pos = mic.get_xyz(with_actuators={"z": "piezo"})["content"]
        assert pos["z"]["actuator"] == "piezo"
        assert pos["x"]["actuator"] == "motoric"  # axes left out use the first motor in the list

    def test_unknown_actuator_raises(self, mic):
        with pytest.raises(ValueError, match="unknown actuator"):
            mic.set_xyz(0, 0, 0, with_actuators={"z": "hovercraft"})


class TestAcquire:
    def test_acquire_returns_record(self, mic):
        rec = mic.acquire(position_label="A1")
        assert rec["success"] is True
        rec = rec["content"]
        assert rec["position_label"] == "A1"
        assert rec["settle"] == "backlash-corrected"  # active default
        assert rec["format"] == "ome-tiff"  # active default
        assert rec["confirmed"] is True
        assert [Path(f).name for f in rec["files"]] == ["A1.ome.tif", "A1.commands.json"]
        assert all(Path(f).is_file() for f in rec["files"])
        assert rec["files"][-1] == rec["command_log"]

    def test_acquire_settings_override(self, mic):
        rec = mic.acquire(
            position_label="B2",
            acquisition_settings={
                "backlash_correction": False,
                "format": "ome-zarr",
                "folder": "targetscan",
            },
        )["content"]
        assert rec["settle"] == "direct"
        assert rec["format"] == "ome-zarr"
        assert [Path(f).name for f in rec["files"]] == ["B2.ome.zarr", "B2.commands.json"]
        assert (Path(rec["files"][0]) / ".zattrs").is_file()

    def test_acquisition_settings_discovered(self, mic):
        opts = mic.get_acquisition_settings()["content"]
        assert opts["backlash_correction"]["active"] is True
        assert "ome-zarr" in opts["format"]["options"]


class TestState:
    def test_state_split_into_changeable_observed(self, mic):
        state = mic.get_state()["content"]
        assert list(state) == ["changeable", "observed"]  # changeable first
        assert "laser_power" in state["changeable"]
        assert "serial" in state["observed"]

    def test_capture_and_reapply(self, mic):
        original = mic.get_state()["content"]
        mic.set_state({"changeable": {"laser_power": 40.0}})
        assert mic.get_state()["content"]["changeable"]["laser_power"] == 40.0
        mic.set_state(original)
        laser = mic.get_state()["content"]["changeable"]["laser_power"]
        assert laser == original["changeable"]["laser_power"]

    def test_set_state_returns_driver_record(self, mic):
        rec = mic.set_state({"changeable": {"laser_power": 7.0}})
        assert rec["success"] is True
        assert rec["content"]["applied"]["laser_power"] == 7.0

    def test_soft_outcome_is_reported_not_raised(self, mic):
        # An empty "changeable" changes nothing, and it is safe to carry on,
        # so the driver says so instead of raising.
        rec = mic.set_state({"changeable": {}})
        assert rec["success"] is False
        assert rec["content"]["applied"] == {}

    def test_unknown_setting_name_is_refused(self, mic):
        # A misspelled name is refused before anything is applied, so a typo
        # never passes silently, not even beside a setting that is correct.
        before = mic.get_state()["content"]["changeable"]["gain"]
        with pytest.raises(ValueError, match="unknown settings \\['gian'\\]"):
            mic.set_state({"changeable": {"gain": before + 1, "gian": 1}})
        assert mic.get_state()["content"]["changeable"]["gain"] == before

    def test_observed_is_a_report_never_an_instruction(self, mic):
        # A mismatching observed part does not block applying the changeable
        # part, because set_state acts on the changeable part only.
        rec = mic.set_state({"changeable": {"laser_power": 5.0}, "observed": {"serial": "OTHER"}})
        assert rec["content"]["applied"]["laser_power"] == 5.0


class TestProcedures:
    def test_get_procedures_lists_available(self, mic):
        assert "autofocus" in mic.get_procedures()["content"]

    def test_run_procedure_returns_driver_record(self, mic):
        rec = mic.run_procedure({"name": "autofocus"})
        assert rec["success"] is True
        assert rec["content"]["ran"] == "autofocus"

    def test_unknown_procedure_is_refused(self, mic):
        with pytest.raises(ValueError, match="unknown procedure"):
            mic.run_procedure({"name": "make_coffee"})


class TestInfo:
    def test_get_info_passthrough(self, mic):
        info = mic.get_info()["content"]
        assert Path(info["output_root"]).is_dir()
        assert info["serial"] == "MOCK-0001"
        # Nothing has been set up yet, so every configuration item is a shipped default.
        assert all(source.endswith("default.json") for source in info["configuration"].values())


class TestDisconnect:
    def test_driver_refusal_reaches_the_caller_unchanged(self, mic):
        # The controller refuses nothing itself; what the driver raises comes through.
        mic.disconnect()
        mic.disconnect()  # the mock driver makes a second disconnect harmless
        with pytest.raises(RuntimeError, match="session is disconnected"):
            mic.acquire(position_label="A1")

    def test_ops_after_disconnect_raise(self, mic):
        mic.disconnect()
        with pytest.raises(RuntimeError, match="disconnected"):
            mic.get_xyz()

    def test_actuator_selection_does_not_persist(self, mic):
        """A motor chosen for one call applies to that call only.

        The next call is back to the default, the first motor in the list."""
        mic.set_xyz(0, 0, 0, with_actuators={"z": "piezo"})
        assert mic.get_xyz()["content"]["z"]["actuator"] == "motoric"

    def test_invalid_acquire_option_rejected(self, mic):
        with pytest.raises(ValueError, match="unknown acquisition setting"):
            mic.acquire(position_label="A1", acquisition_settings={"fromat": "x"})
        with pytest.raises(ValueError, match="invalid value"):
            mic.acquire(position_label="A1", acquisition_settings={"format": "png"})


class TestModuleStyle:
    def test_module_delegates_to_active_microscope(self):
        import zmart_controller as m

        m.set_instrument(mock)
        m.set_xyz(10, 20, 5)
        assert m.get_xyz()["content"]["x"]["value"] == 10
        m.disconnect()

    def test_module_disconnect_clears_active(self):
        import zmart_controller as m

        m.set_instrument(mock)
        m.disconnect()
        with pytest.raises(AttributeError, match="no active microscope"):
            m.acquire(position_label="A1")
        m.disconnect()  # no active microscope: still a no-op

    def test_swap_survives_failing_teardown(self):
        import zmart_controller as m

        first = m.set_instrument(mock)
        first.disconnect = lambda: (_ for _ in ()).throw(RuntimeError("teardown boom"))
        with pytest.raises(RuntimeError, match="teardown boom"):
            m.set_instrument(mock)
        # the new session must be tracked despite the old teardown failing
        m.set_xyz(1, 2, 3)
        assert m.get_xyz()["content"]["x"]["value"] == 1

    def test_no_active_session_error_is_helpful(self):
        import zmart_controller as m

        with pytest.raises(AttributeError, match="set_instrument"):
            m.acquire(position_label="A1")

    def test_unknown_attribute_raises(self):
        import zmart_controller as m

        missing = "definitely_not_a_method"
        with pytest.raises(AttributeError):
            getattr(m, missing)


class TestCanvas:
    def test_the_canvas_is_the_travel_widened_by_half_the_widest_field(self):
        """At the edge of travel a picture still shows half a field further out.

        The mock's widest field is the 10x objective's: 64 pixels of 1.0 µm,
        so on x and y the canvas reaches 32 µm past the travel. Its z-stacks
        must stay inside the travel, so on z the canvas is the travel itself.
        """
        from zmart_controller.mock.configuration import save
        from zmart_controller.session import set_instrument as open_session

        save("origin", {"x": 51_000.0, "y": 37_500.0, "z": 5_000.0})
        session = open_session(mock)
        try:
            content = session.get_xyz()["content"]
            assert content["x"]["canvas"] == [-6032.0, 4032.0]
            assert content["y"]["canvas"] == [-5032.0, 5032.0]
            assert content["z"]["canvas"] == [-500.0, 500.0]  # exactly the z travel
        finally:
            session.disconnect()

    def test_a_move_outside_the_range_is_refused_before_moving(self, mic):
        mic.set_xyz(10, 0, 0)
        with pytest.raises(ValueError, match="outside the travel range"):
            mic.set_xyz(9999, 0, 0)
        assert mic.get_xyz()["content"]["x"]["value"] == 10  # did not move


def _driver_folder(tmp_path, name="bench", connection=None, package=False):
    """A driver folder on disk, with its zmart_controller_plugin.py.

    The plug-in passes every call on to the mock. With ``package``, the
    folder is a package and the plug-in uses a relative import, as real
    drivers do.
    """
    folder = tmp_path / "drivers" / f"{name}_driver"
    folder.mkdir(parents=True)
    header = f"NAME = {name!r}\nCONNECTION = {connection or {}!r}\n"
    if package:
        (folder / "__init__.py").write_text("")
        (folder / "helpers.py").write_text("from zmart_controller.mock import *  # noqa\n")
        body = "from .helpers import *  # noqa\n"
    else:
        body = "from zmart_controller.mock import *  # noqa\n"
    # The mock's own NAME and CONNECTION come in with the *, so this file's go last.
    (folder / "zmart_controller_plugin.py").write_text(body + header)
    return folder


class TestRegisteredDrivers:
    def test_the_mock_is_always_listed(self):
        import zmart_controller

        assert list(zmart_controller.get_instruments()) == ["mock"]

    def test_register_once_then_plug_in_by_name(self, tmp_path):
        import zmart_controller

        folder = _driver_folder(tmp_path, connection={"client": "bench-pc"})
        assert zmart_controller.register_driver(folder) == "bench"
        assert list(zmart_controller.get_instruments()) == ["mock", "bench"]
        session = zmart_controller.set_instrument("bench")
        assert session.context == {"driver": "bench"}
        assert session.get_info()["content"]["client"] == "bench-pc"  # its CONNECTION

    def test_a_driver_that_is_a_package_with_relative_imports(self, tmp_path):
        import zmart_controller

        zmart_controller.register_driver(_driver_folder(tmp_path, "pkg", package=True))
        session = zmart_controller.set_instrument("pkg")
        assert session.get_xyz()["success"] is True

    def test_a_folder_without_the_plugin_file_is_refused(self, tmp_path):
        import zmart_controller

        with pytest.raises(ValueError, match="zmart_controller_plugin.py"):
            zmart_controller.register_driver(tmp_path)
        assert list(zmart_controller.get_instruments()) == ["mock"]

    def test_a_driver_missing_a_function_is_refused_and_not_saved(self, tmp_path):
        import zmart_controller

        folder = _driver_folder(tmp_path)
        (folder / "zmart_controller_plugin.py").write_text(
            "NAME = 'bench'\ndef connect(connection):\n    return None\n"
        )
        with pytest.raises(ValueError, match="missing functions"):
            zmart_controller.register_driver(folder)
        assert list(zmart_controller.get_instruments()) == ["mock"]

    def test_the_plugin_file_itself_can_be_given(self, tmp_path):
        import zmart_controller

        plugin = _driver_folder(tmp_path) / "zmart_controller_plugin.py"
        assert zmart_controller.register_driver(plugin) == "bench"

    def test_a_plugin_without_a_name_is_refused(self, tmp_path):
        import zmart_controller

        folder = _driver_folder(tmp_path)
        (folder / "zmart_controller_plugin.py").write_text(
            "from zmart_controller.mock import *\nNAME = ''\n"
        )
        with pytest.raises(ValueError, match="must give the driver's NAME"):
            zmart_controller.register_driver(folder)

    def test_an_unknown_name_is_refused(self):
        import zmart_controller

        with pytest.raises(ValueError, match="no driver installed as 'ghost'"):
            zmart_controller.set_instrument("ghost")

    def test_remove_driver(self, tmp_path):
        import zmart_controller

        zmart_controller.register_driver(_driver_folder(tmp_path))
        assert zmart_controller.remove_driver("bench") is True
        assert zmart_controller.remove_driver("bench") is False
        assert list(zmart_controller.get_instruments()) == ["mock"]

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows folders ignore chmod")
    def test_falls_back_to_the_home_folder_when_the_computers_folder_is_read_only(
        self, tmp_path, monkeypatch
    ):
        import zmart_controller
        from zmart_controller import utils

        shared = tmp_path / "read-only"
        shared.mkdir()
        shared.chmod(0o500)
        monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(shared))
        try:
            zmart_controller.register_driver(_driver_folder(tmp_path))
            assert (utils.user_root() / "drivers.json").is_file()
            assert list(zmart_controller.get_instruments()) == ["mock", "bench"]
        finally:
            shared.chmod(0o700)
