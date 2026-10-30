# Publish Validator

Extensible sanity checks to run before publishing assets: modeling, lookdev,
rigging and so on. It works in Blender (primary), Maya and Houdini, and can be
adapted to any application that runs Python 3.11 or newer.

- **Adding a check means writing one small class.** See [docs/writing-checks.md](docs/writing-checks.md).
- **Studios configure it without touching code.** Layered TOML config lets them enable or disable checks, change severities and tune settings.
- **It runs with or without a UI.** There's a native Blender sidebar panel, plus a CLI and a JSON report for publish hooks and farm jobs.
- **The core has no dependencies.** It's pure standard library and never imports a DCC, so it's testable anywhere.

## Quick start (Blender)

1. Mark an asset root, usually an Empty with the asset parented under it, with custom properties:

   | Property | Example | |
   |---|---|---|
   | `pv_task` | `model` | required: marks the root |
   | `pv_asset_type` | `prop` | |
   | `pv_asset_name` | `chair` | defaults to the object's name |

2. Install the extension: `python scripts/build_blender_extension.py`, then
   Preferences > Get Extensions > Install from Disk > `dist/publish_validator-*.zip`.
3. Select anything in the asset, open **View3D > Sidebar (N) > Validate**, and
   press **Validate** or **Fix**.

For development, skip the build and start Blender with the source on the path:

```bash
PYTHONPATH=$PWD/src blender
```

then run `import publish_validator.hosts.blender as b; b.register()` in the
Python console.

### Headless / publish hook

```bash
blender -b scene.blend --python-exit-code 1 \
  --python-expr "import sys; from publish_validator.cli import main; sys.exit(main())" \
  -- --all --json
```

Exit code: 0 means nothing blocks the publish, 1 means blocked, 2 means a usage error.

From Python inside any host:

```python
from publish_validator import Validator, format_text
from publish_validator.hosts import current_host

report = Validator(current_host()).run()   # validates the selected asset
print(format_text(report))
if not report.passed:
    raise RuntimeError("publish blocked")
```

## How it fits together

```
 Host ──selection──▶ Resolver ──Subject──▶ Registry.applicable() ──checks──▶ Runner ──▶ Report
 (Blender/Maya/…)    (pv_* props,         (filters by host,                (isolates     (text, JSON,
                      or your pipeline)    task, asset type)                 errors, fix,  UI, exit code)
                                                                             re-validate)
                      Config (TOML layers) ─────────────────────────────────┘
```

| Piece | Where | Responsibility |
|---|---|---|
| `Check` | `core/check.py` | Base class: metadata, settings, `validate` and optional `fix` |
| `discover` / `Registry` | `core/discovery.py`, `core/registry.py` | Load built-in, entry-point and folder checks; report load errors and duplicate ids |
| `Config` | `core/config.py` | Layered TOML: check paths, resolver, per-check overrides |
| `Subject` / resolvers | `core/subject.py` | What is being validated. `PropertyResolver` is the default |
| `Host` | `core/host.py` | Small adapter interface per application |
| `run` / `Observer` | `core/runner.py` | Runs checks, catches errors per check, fixes and re-validates, emits progress events |
| `Validator` | `core/validator.py` | Facade used by the UI, CLI and hooks |
| Hosts | `hosts/blender` (full), `hosts/maya`, `hosts/houdini` (untested stubs) | Scene access, selection, the Blender UI |

### Plugging in a pipeline

To read asset info from your pipeline instead of `pv_*` properties, write a
resolver and name it in config:

```python
class PipelineResolver:
    def resolve(self, host, node=None) -> Subject: ...   # raise ResolveError("message for artist")
    def find_all(self, host) -> list[Subject]: ...
```

```toml
resolver = "my_pipeline.validator:PipelineResolver"
```

The simplest route is to subclass `PropertyResolver`; for example, set
`prefix = "studio_"` to use different property names.

### Supporting another application

Subclass `publish_validator.Host` and implement `selection`, `select`, `find`,
`parent`, `children`, `get_property` and `find_by_property`. Then add it to
`HOSTS` in `hosts/__init__.py`. Add any helper methods your checks need.

## Development

```bash
uv run --python 3.11 --group dev pytest        # core tests (also run on 3.13)
uv run --group dev ruff check && uv run --group dev ruff format --check
blender -b --factory-startup --python-exit-code 1 --python tests/blender/run.py
publish-validator --list --path examples/studio_checks
```

The code targets Python 3.11 syntax (Maya 2026) and is tested on 3.13
(Blender 5.1+). Don't use 3.12+ only syntax.

`Inspiration/` (ignored by git) holds the previous PAV tool, kept for reference
while porting its checks.
