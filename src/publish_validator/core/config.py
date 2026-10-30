"""Studio and project settings, read from TOML files.

The files listed in PUBLISH_VALIDATOR_CONFIG are read in order and later files
win, so the usual setup is a studio file followed by a project file:

    PUBLISH_VALIDATOR_CONFIG=/studio/validator.toml:/projects/foo/validator.toml

See examples/studio_checks/studio.toml for everything a file can contain.
"""

import os
import tomllib
from pathlib import Path

from .results import SEVERITIES

CONFIG_ENV = "PUBLISH_VALIDATOR_CONFIG"


class ConfigError(Exception):
    pass


class Config:
    def __init__(self):
        self.check_paths = []  # extra folders to load checks from
        self.resolver = None  # "module:Class" of a custom resolver
        self.checks = {}  # check name -> {"enabled": .., "severity": .., "settings": {..}}

    def read(self, path):
        """Merge one TOML file into this config. Values in it override earlier files."""
        path = Path(path)
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ConfigError(f"Could not read config {path}: {error}") from error

        unknown = set(data) - {"check_paths", "resolver", "checks"}
        if unknown:
            raise ConfigError(f"{path}: unknown option(s) {', '.join(sorted(unknown))}")

        for folder in data.get("check_paths", []):
            # Relative folders are relative to the config file, not the working directory.
            self.check_paths.append(path.parent / os.path.expandvars(folder))

        self.resolver = data.get("resolver", self.resolver)

        for name, options in data.get("checks", {}).items():
            unknown = set(options) - {"enabled", "severity", "settings"}
            if unknown:
                raise ConfigError(f"{path}: unknown option(s) for {name}: {', '.join(unknown)}")
            severity = options.get("severity")
            if severity is not None and severity not in SEVERITIES:
                raise ConfigError(
                    f"{path}: severity for {name} must be one of {', '.join(SEVERITIES)}"
                )

            current = self.checks.setdefault(name, {"settings": {}})
            for key in ("enabled", "severity"):
                if key in options:
                    current[key] = options[key]
            current["settings"].update(options.get("settings", {}))

    def for_check(self, name):
        return self.checks.get(name, {"settings": {}})


def load_config(paths=()):
    """Read the files in PUBLISH_VALIDATOR_CONFIG, then any extra paths given."""
    config = Config()
    env_paths = os.environ.get(CONFIG_ENV, "").split(os.pathsep)
    for path in [*env_paths, *paths]:
        if path:
            config.read(path)
    return config
