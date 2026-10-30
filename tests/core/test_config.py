import pytest

from publish_validator import ConfigError, Severity, load_config
from publish_validator.core.config import ENV_CONFIG, parse_config


def write(path, text):
    path.write_text(text)
    return path


def test_parse_and_resolve_relative_paths(tmp_path):
    path = write(
        tmp_path / "studio.toml",
        """
check_paths = ["checks"]
resolver = "pkg.mod:Resolver"

[checks."transforms.unit_scale"]
severity = "warning"
settings = { tolerance = 0.01 }
""",
    )
    config = load_config([path], use_env=False)
    assert config.check_paths == ((tmp_path / "checks").resolve(),)
    assert config.resolver == "pkg.mod:Resolver"
    entry = config.for_check("transforms.unit_scale")
    assert entry.severity is Severity.WARNING
    assert entry.settings == {"tolerance": 0.01}


def test_layers_merge_later_wins(tmp_path, monkeypatch):
    studio = write(
        tmp_path / "studio.toml",
        '[checks."a.b"]\nseverity = "error"\nsettings = { x = 1, y = 2 }\n',
    )
    project = write(tmp_path / "project.toml", '[checks."a.b"]\nsettings = { y = 3 }\n')
    user = write(tmp_path / "user.toml", '[checks."a.b"]\nenabled = false\n')
    monkeypatch.setenv(ENV_CONFIG, f"{studio}:{project}")
    entry = load_config([user]).for_check("a.b")
    assert entry.enabled is False
    assert entry.severity is Severity.ERROR
    assert entry.settings == {"x": 1, "y": 3}


def test_patterns_then_exact_id():
    config = parse_config(
        {
            "checks": {
                "a.b": {"enabled": True},
                "a.*": {"enabled": False, "severity": "warning"},
            }
        }
    )
    assert config.for_check("a.b").enabled is True
    assert config.for_check("a.b").severity is Severity.WARNING
    assert config.for_check("a.c").enabled is False
    assert config.for_check("z.z").enabled is None


def test_unknown_ids():
    config = parse_config({"checks": {"a.b": {}, "typo.id": {}, "a.*": {}}})
    assert config.unknown_ids(["a.b"]) == ["typo.id"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"chekcs": {}}, "unknown key"),
        ({"checks": {"a": {"enable": True}}}, "unknown key"),
        ({"checks": {"a": {"severity": "fatal"}}}, "severity must be one of"),
        ({"checks": {"a": {"enabled": "yes"}}}, "enabled must be"),
        ({"resolver": "no_colon"}, "module:Class"),
        ({"check_paths": "single"}, "list of strings"),
    ],
)
def test_validation_errors(data, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(data)


def test_bad_toml_and_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config([tmp_path / "missing.toml"], use_env=False)
    bad = write(tmp_path / "bad.toml", "checks = [")
    with pytest.raises(ConfigError, match=r"bad\.toml"):
        load_config([bad], use_env=False)
