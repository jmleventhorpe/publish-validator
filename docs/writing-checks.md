# Writing checks

A check is a small Python class. You write one file, put it in a folder the
validator knows about, and it shows up in the UI, the CLI and publish hooks.
There is nothing to register.

## 1. The smallest check

```python
# my_checks/hierarchy.py
from publish_validator import Check


class HasGeoGroup(Check):
    """The asset root must contain a 'geo' group.

    Everything downstream looks for geometry under 'geo'.
    Create an empty called 'geo' under the root and parent the meshes to it.
    """

    def validate(self, ctx):
        names = [ctx.host.node_name(n) for n in ctx.host.children(ctx.root)]
        if "geo" not in names:
            yield self.issue("No 'geo' group under the asset root", ctx.root)
```

- **`validate(ctx)`** yields one issue per problem. If it yields nothing, the check passes.
- **`self.issue(message, *targets)`**: the targets are the scene objects involved. They're what the **Select** button selects.
- **The docstring is the documentation.** The first line is a summary; the rest should say why it matters and how to fix it by hand. The UI shows it as a tooltip.
- **You can also yield a plain string**, which is the same as an issue with no targets.

## 2. Make it load

Put the file in a folder and point the validator at it, in either of two ways:

```bash
export PUBLISH_VALIDATOR_PATH=/studio/pipeline/my_checks      # ":"-separated (";" on Windows)
```

or in a config file (see section 6):

```toml
check_paths = ["my_checks"]       # relative to the config file
```

Every `.py` file in the folder, including subfolders, is loaded. Some rules:

| Rule | Why |
|---|---|
| Files and folders starting with `_` or `.` are skipped | Put shared helpers in `_utils.py` |
| A folder named after a host (`blender/`, `maya/`, `houdini/`) only loads in that host | Keeps host-specific code out of other apps |
| A file that fails because `bpy`/`maya`/`hou` isn't importable is skipped silently | Host-only files are harmless elsewhere |
| A file that fails for any other reason is listed as a **load error** | One broken file never stops the others |
| Files are re-executed on every discovery (the ↻ button in Blender) | Edit and reload without restarting |

A pip-installable package can expose checks through the entry-point group
`publish_validator.checks`, pointing at a module, a Check class, or a function
that returns Check classes:

```toml
# your package's pyproject.toml
[project.entry-points."publish_validator.checks"]
my_studio = "my_studio.checks"
```

## 3. Say where it applies

Every attribute is optional:

```python
class UnitScale(Check):
    """Mesh objects must have a scale of (1, 1, 1)."""

    id = "studio.unit_scale"      # stable id for config; default "<file>.<snake_case_class>"
    label = "Unit Scale"          # UI name; default is the class name spaced out
    category = "Transforms"       # UI group
    hosts = {"blender"}           # None (default) = every host
    tasks = {"model"}             # None = every task
    asset_types = {"prop", "character"}
    severity = Severity.ERROR     # ERROR blocks publishing; WARNING and INFO don't
    enabled = True                # False = studios must opt in through config
    order = 0                     # lower runs first
```

Set `id` explicitly for anything other studios or configs will reference. The
default id changes if you rename the file or the class.

A check limited to one host (for example `hosts = {"blender"}`) can use that
host's helpers, such as `ctx.host.meshes(root)` and `ctx.host.apply_scale(objs)`
in Blender, and can use `bpy` directly. A check with no `hosts` should stick to
the generic host API:

| Method | Returns |
|---|---|
| `ctx.host.children(node)` | Direct children of a node |
| `ctx.host.descendants(node)` | Everything below a node |
| `ctx.host.parent(node)` | A node's parent |
| `ctx.host.node_name(node)` | A node's short name |
| `ctx.host.get_property(node, key, default)` | A custom property's value |
| `ctx.host.find(name)` | A node by name |
| `ctx.host.selection()` / `ctx.host.select(targets)` | The current selection / select targets |

## 4. Settings: let studios tune it without editing code

```python
class UnitScale(Check):
    class Settings:
        tolerance = 1e-6
        ignore = ["proxy"]        # lists are fine; they become tuples

    def validate(self, ctx):
        tolerance = self.settings.tolerance
        ...
```

Studios override settings per project in config. Unknown setting names are
reported as errors, so typos don't fail silently.

## 5. Automatic fixes

Add a `fix` method and the check becomes fixable (the **Fix** button and
`--fix`):

```python
    def validate(self, ctx):
        for obj in ctx.host.meshes(ctx.root):
            if tuple(obj.scale) != (1, 1, 1):
                yield self.issue(f"{obj.name} is scaled", obj)

    def fix(self, ctx, issues):
        for issue in issues:
            ctx.host.apply_scale(issue.targets)
```

You don't need to report what got fixed. The runner calls `validate` again
after `fix`, and reports the check as **FIXED** if nothing is left, or as
FAILED with whatever remains.

To pass extra data from `validate` to `fix`, use keyword arguments:
`self.issue("msg", obj, expected="map1")` puts `expected` into `issue.data["expected"]`.

## 6. Configure without code

```toml
# studio.toml
check_paths = ["checks"]

[checks."transforms.unit_scale"]
severity = "warning"                      # downgrade for this studio
settings = { tolerance = 0.0001 }

[checks."studio.geo_naming".settings]
pattern = "^[A-Z][A-Za-z0-9]*$"

[checks."legacy.*"]                       # glob patterns work; exact ids win
enabled = false
```

Layer files with `PUBLISH_VALIDATOR_CONFIG` (studio first, then more specific
files). Later files win:

```bash
export PUBLISH_VALIDATOR_CONFIG=/studio/pv.toml:/projects/foo/pv.toml
```

## 7. Function shortcut

For very simple checks, a decorated function works too. It becomes the same
kind of Check class:

```python
from publish_validator import check

@check(category="Hierarchy", settings={"max_depth": 6})
def not_too_deep(ctx):
    """Hierarchies deeper than max_depth are hard to work with."""
    ...
    yield "Hierarchy is 9 levels deep"

@not_too_deep.fixer          # optional
def _(ctx, issues):
    ...
```

Settings come through `ctx.settings`.

## 8. Share work between checks

`ctx.cached(key, factory)` computes a value once per run and shares it with
every check:

```python
meshes = ctx.cached("meshes", lambda: ctx.host.meshes(ctx.root))
```

## 9. Precise targets: components

To point at specific faces, edges or vertices instead of the whole object,
use `Component`:

```python
from publish_validator import Component

yield self.issue(f"{obj.name} has {len(faces)} ngons", Component(obj, "face", tuple(faces)))
```

In Blender, **Select** enters Edit Mode with exactly those elements selected.

## 10. Test it

Generic checks can be tested with plain pytest, without opening a DCC:

```python
from publish_validator import Status
from publish_validator.testing import FakeNode, run_check
from my_checks.hierarchy import HasGeoGroup

def test_missing_geo():
    root = FakeNode("chair", FakeNode("render"), props={"pv_task": "model"})
    assert run_check(HasGeoGroup, root).status is Status.FAILED
```

`FakeNode` accepts any attributes (`FakeNode("cube", scale=(2, 1, 1))`).
Host-specific checks are best tested inside the host. See
`tests/blender/run.py` for the pattern.

To check what is loaded and where each check applies:

```bash
publish-validator --list --path my_checks
```
