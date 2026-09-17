from __future__ import annotations

from pathlib import Path

from app.config import AppSettings
from app.db import _alembic_config, _core_root


def _settings_with(tmp_path: Path) -> AppSettings:
    return AppSettings(data_dir=tmp_path)


def test_core_root_defaults_to_source_tree():
    root = _core_root()
    assert (root / "alembic.ini").is_file()
    assert (root / "alembic" / "env.py").is_file()


def test_core_root_uses_the_frozen_bundle_root(monkeypatch, tmp_path):
    """In the PyInstaller onedir sidecar, alembic.ini + alembic/ ship as
    datas under sys._MEIPASS (the _internal/ directory next to the exe)."""
    fake_bundle = tmp_path / "_internal"
    (fake_bundle / "alembic" / "versions").mkdir(parents=True)
    (fake_bundle / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    monkeypatch.setattr("sys._MEIPASS", str(fake_bundle), raising=False)

    root = _core_root()

    assert root == fake_bundle
    assert (root / "alembic.ini").is_file()


def test_alembic_config_locates_scripts_from_frozen_bundle_root(monkeypatch, tmp_path):
    fake_bundle = tmp_path / "_internal"
    (fake_bundle / "alembic").mkdir(parents=True)
    (fake_bundle / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    monkeypatch.setattr("sys._MEIPASS", str(fake_bundle), raising=False)

    config = _alembic_config(_settings_with(tmp_path))

    assert config.get_main_option("script_location") == str(fake_bundle / "alembic")


def test_alembic_config_defaults_to_source_tree(tmp_path):
    config = _alembic_config(_settings_with(tmp_path))

    assert config.get_main_option("script_location").endswith("alembic")
    assert Path(config.config_file_name).exists()
