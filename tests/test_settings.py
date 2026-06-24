# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Tests for testrig.settings."""

from testrig.settings import DEFAULT_SETTINGS, load_settings


def write_toml(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    return str(path)


class TestLoadSettings:
    def test_returns_defaults_when_no_files_exist(self, tmp_path):
        missing = [str(tmp_path / "etc.toml"), str(tmp_path / "home.toml")]

        settings = load_settings(paths=missing)

        assert settings == DEFAULT_SETTINGS
        assert settings["disable_debug"] is False
        assert settings["ROCR_VISIBLE_DEVICES"] == ""

    def test_does_not_mutate_default_settings(self, tmp_path):
        path = write_toml(tmp_path / "settings.toml", "disable_debug = true\n")

        load_settings(paths=[path])

        assert DEFAULT_SETTINGS["disable_debug"] is False

    def test_loads_value_from_file(self, tmp_path):
        path = write_toml(tmp_path / "settings.toml", "disable_debug = true\n")

        settings = load_settings(paths=[path])

        assert settings["disable_debug"] is True

    def test_later_path_overrides_earlier(self, tmp_path):
        etc = write_toml(tmp_path / "etc.toml", "disable_debug = false\n")
        home = write_toml(tmp_path / "home.toml", "disable_debug = true\n")

        settings = load_settings(paths=[etc, home])

        assert settings["disable_debug"] is True

    def test_missing_higher_precedence_file_keeps_lower(self, tmp_path):
        etc = write_toml(tmp_path / "etc.toml", "disable_debug = true\n")
        home = str(tmp_path / "missing-home.toml")

        settings = load_settings(paths=[etc, home])

        assert settings["disable_debug"] is True

    def test_partial_file_keeps_other_defaults(self, tmp_path):
        path = write_toml(tmp_path / "settings.toml", "unknown_option = 42\n")

        settings = load_settings(paths=[path])

        assert settings["disable_debug"] is False
        assert settings["ROCR_VISIBLE_DEVICES"] == ""
        assert settings["unknown_option"] == 42

    def test_loads_rocr_visible_devices_from_file(self, tmp_path):
        path = write_toml(tmp_path / "settings.toml", 'ROCR_VISIBLE_DEVICES = "GPU-123"\n')

        settings = load_settings(paths=[path])

        assert settings["ROCR_VISIBLE_DEVICES"] == "GPU-123"
