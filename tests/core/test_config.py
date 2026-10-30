import pytest

from publish_validator import ConfigError, load_config
from publish_validator.core.config import CONFIG_ENV


def test_read_a_file(tmp_path):
    path = tmp_path / "studio.toml"
    path.write_text(
        'check_paths = ["checks"]\n'
        'resolver = "pipeline:Resolver"\n'
        "[checks.UnitScale]\n"
        'severity = "warning"\n'
        "settings = { tolerance = 0.01 }\n"
    )
    config = load_config([path])
    assert config.check_paths == [tmp_path / "checks"]
    assert config.resolver == "pipeline:Resolver"
    assert config.for_check("UnitScale") == {
        "severity": "warning",
        "settings": {"tolerance": 0.01},
    }
    assert config.for_check("Other") == {"settings": {}}


def test_later_files_win(tmp_path, monkeypatch):
    studio = tmp_path / "studio.toml"
    studio.write_text('[checks.A]\nseverity = "error"\nsettings = { x = 1, y = 2 }\n')
    project = tmp_path / "project.toml"
    project.write_text("[checks.A]\nenabled = false\nsettings = { y = 3 }\n")
    monkeypatch.setenv(CONFIG_ENV, str(studio))

    options = load_config([project]).for_check("A")
    assert options == {"severity": "error", "enabled": False, "settings": {"x": 1, "y": 3}}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("chekcs = 1", "unknown option"),
        ("[checks.A]\nenable = true", "unknown option"),
        ('[checks.A]\nseverity = "fatal"', "severity for A must be"),
        ("checks = [", "Could not read"),
        ('[checks.A]\nenabled = "false"', "true or false, without quotes"),
        ("[checks.A]\nsettings = 5", "must be a table"),
        ('check_paths = "checks"', "must be a list"),
        ('resolver = "no_colon"', "module:ClassName"),
    ],
)
def test_mistakes_are_reported(tmp_path, text, message):
    path = tmp_path / "bad.toml"
    path.write_text(text)
    with pytest.raises(ConfigError, match=message):
        load_config([path])


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="Could not read"):
        load_config([tmp_path / "missing.toml"])
