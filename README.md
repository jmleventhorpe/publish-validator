# Publish Validator

Sanity checks to run before publishing an asset (modeling, lookdev, rigging and
so on). Blender is the main target, followed by Maya and Houdini. It runs in any
application with Python 3.11 or newer.

- **Adding a check means writing one small class.** See [docs/writing-checks.md](docs/writing-checks.md).
- **Studios change behaviour in a TOML config file,** not in the code.
- **It runs with or without a UI:** a Blender sidebar panel, plus a command line for publish hooks and the farm.

## Using it in Blender

1. **Mark the asset's root** (usually an Empty with the asset parented under it) with custom properties:

   | Property | Example | Notes |
   |---|---|---|
   | `pv_task` | `model` | Required. This is what marks the root |
   | `pv_asset_type` | `prop` | |
   | `pv_asset_name` | `chair` | Optional. Defaults to the object's name |

2. **Install the extension:** run `python scripts/build_blender_extension.py`, then go to Preferences > Get Extensions > Install from Disk and pick `dist/publish_validator-*.zip`.
3. **Run it:** select anything in the asset, open View3D > Sidebar (N) > **Validate**, and press **Validate**.

The panel lists every check that applies, grouped by category, with a green, orange
or red icon once validated. Click a check to see its details and the problems it
found. Untick checks to skip them while you work (a headless publish still runs them all).
Each row has its own Fix and Select buttons, and **Fix All** fixes everything that
can fix itself. If you change the asset after validating, the panel says the results
are out of date.

To try it without installing anything, run the demo, which builds a test asset with
a few deliberate problems:

```bash
blender --python scripts/blender_demo.py
```

## Without a UI

```bash
blender -b scene.blend --python-exit-code 1 \
  --python-expr "import sys; from publish_validator.cli import main; sys.exit(main())" \
  -- --all
```

The exit code is 0 if nothing blocks the publish, 1 if something does, and 2 for
usage errors. Add `--json` for a machine-readable report.

From Python, inside any of the supported applications:

```python
from publish_validator import Validator
from publish_validator.hosts import current_host

report = Validator(current_host()).run()   # validates the selected asset
print(report.as_text())
```

## Built-in checks

All of these run for the **model** task. Studios can switch any off, change its
severity or tune its settings in config (see [docs/writing-checks.md](docs/writing-checks.md)).
None of the checks below fix anything automatically, except Unit Scale.

| Check | Category | Looks for |
|---|---|---|
| Root Not Empty | Structure | An asset root with nothing under it |
| Group Setup | Structure | The standard layout: root > `geo` (> `render`, `proxy`) and `simproxy` |
| Allowed Object Types | Structure | Cameras, lights and other non-mesh, non-empty objects |
| Geo Children | Structure | Meshes parented under other meshes |
| Naming Convention | Naming | `seat`, `L_frontLeg`, `legs`, and `seat_proxy` under proxy; no `.001` endings |
| Mesh Data Names | Naming | Mesh data named differently from its object |
| Unit Scale | Transforms | Mesh objects with a scale other than 1 (can fix) |
| Zero Transforms | Transforms | Objects whose origin isn't at the world centre, or that are rotated |
| Has Animation | Transforms | Keyframes, drivers or NLA tracks |
| Unapplied Modifiers | Geometry | Modifiers other than Subdivision (warning) |
| Ngons | Geometry | Faces with more than 4 corners |
| Zero Area Faces | Geometry | Faces squashed flat to nothing |
| Lamina Faces | Geometry | Faces that share all their corners with another face |
| Double Verts | Geometry | Vertices sitting on top of each other |
| Non Manifold | Geometry | Edges shared by more than two faces |
| Mesh Holes | Geometry | Open borders, i.e. edges with a face on one side only (warning) |

Every check except Root Not Empty and Group Setup is Blender-only for now.

## How it works

See [docs/architecture.md](docs/architecture.md) for diagrams of how the pieces
connect.

```
selection ─▶ resolver ─▶ subject ─▶ checks that apply ─▶ run each check ─▶ report
             (finds the    (name,     (by host, task       (a crash in one     (panel, text,
              asset root)   type,      and asset type)      check never stops   JSON, exit code)
                            task)                           the others)
```

| File | What it does |
|---|---|
| `core/check.py` | `Check`, the base class every check inherits from, and `Context`, what a check gets to work with |
| `core/validator.py` | `Validator`, the object the panel and command line use, plus the code that runs each check |
| `core/loader.py` | Finds check files in folders and loads them |
| `core/config.py` | Reads the studio and project TOML files |
| `core/subject.py` | Works out which asset is selected (`PropertyResolver`) |
| `core/host.py` | `Host`, the base class for each application |
| `core/results.py` | Issues, results and the report (with text and JSON output) |
| `hosts/blender/` | The Blender host and sidebar panel |
| `hosts/maya/`, `hosts/houdini/` | Hosts for Maya and Houdini. Not yet tested in either application |
| `checks/` | Built-in checks |
| `testing.py` | `FakeNode` and `FakeHost`, for testing checks without an application |

### Using your pipeline's asset data

If your pipeline stores asset information somewhere other than `pv_*`
properties, write a resolver class with `resolve(host, node=None)` and
`find_all(host)` methods. Then name it in config:

```toml
resolver = "my_pipeline.validator:PipelineResolver"
```

Subclassing `PropertyResolver` is the easiest start. For example, set
`prefix = "studio_"` to read `studio_task` and so on.

### Supporting another application

Subclass `Host` and fill in `selection`, `select`, `find`, `parent`, `children`,
`get_property` and `find_by_property`. Then add the application to
`current_host()` in `hosts/__init__.py`.

## Development

```bash
uv run --python 3.11 --group dev pytest     # core tests (also run them with --python 3.13)
uv run --group dev ruff check
blender -b --factory-startup --python-exit-code 1 --python tests/blender/run.py
```

Write code for Python 3.11 (Maya 2026); Blender 5.1+ uses 3.13.

`Inspiration/` (not in git) holds the old PAV tool for reference.
