# Writing checks

A check is a small Python class in a `.py` file. Put the file in a check folder
and it shows up in the panel and on the command line. There is nothing to
register.

## A first check

```python
# my_checks/hierarchy.py
from publish_validator import Check


class HasGeoGroup(Check):
    """The asset needs a 'geo' group.

    Everything downstream looks for geometry under 'geo'. Create an empty called
    'geo' under the asset root and parent the meshes to it.
    """

    category = "Hierarchy"

    def validate(self, ctx):
        names = [ctx.host.node_name(node) for node in ctx.host.children(ctx.root)]
        if "geo" not in names:
            yield self.issue("There is no 'geo' group", ctx.root)
```

- **`validate`** yields one issue per problem it finds. If it yields nothing, the check passed.
- **`self.issue(message, *targets)`** creates an issue. The targets are the scene objects involved; the **Select** button selects them.
- **A plain string** can be yielded instead, for an issue with nothing to select.
- **The docstring** is shown as the check's tooltip. The first line says what the rule is; the rest says why it matters and how to fix it by hand.
- **The class name** (`HasGeoGroup`) identifies the check in config files and reports, so keep it unique.

## Where check files go

Any of these folders is loaded:

- `src/publish_validator/checks/` (the built-in checks)
- folders listed in `check_paths` in a config file
- folders listed in the `PUBLISH_VALIDATOR_PATH` environment variable (separated by `:`, or `;` on Windows)

Every `.py` file in those folders is loaded, including files in subfolders, with these rules:

- **Files and folders starting with `_` are not loaded as checks.** Use that for shared helper code: a check can `from _utils import ...` a helper file in its own folder, and ↻ reloads helpers too.
- **A folder called `blender`, `maya` or `houdini` only loads in that application.**
- **A file that can't import `bpy`, `maya` or `hou` is skipped quietly** when you're in a different application.
- **Any other error in a file is shown as "could not load".** The other files still load.
- **The ↻ button in the Blender panel loads every file again,** so you can edit a check without restarting Blender.

## Where a check runs

```python
class UnitScale(Check):
    label = "Unit Scale"          # name in the UI (default: the class name with spaces)
    category = "Transforms"       # group in the UI
    hosts = ["blender"]           # only in Blender (default: every application)
    tasks = ["model"]             # only for modeling (default: every task)
    asset_types = ["prop"]        # only for props (default: every type)
    severity = WARNING            # INFO, WARNING or ERROR (default). Only ERROR blocks a publish.
    enabled = False               # off unless a studio switches it on in config
```

Every one of these is optional.

**Host methods.** A check with no `hosts` should only use the host methods that
every application has:

| Method | Returns |
|---|---|
| `ctx.host.children(node)` | The node's direct children |
| `ctx.host.descendants(node)` | Everything below the node |
| `ctx.host.parent(node)` | The node's parent |
| `ctx.host.node_name(node)` | The node's short name |
| `ctx.host.get_property(node, key)` | A custom property on the node |
| `ctx.host.find(name)` | The node with that name |

A check limited to Blender can use Blender's helpers (`ctx.host.meshes(root)`,
`ctx.host.apply_scale(objects)`) and `bpy` itself.

**The context.** `ctx` holds everything about the current run:

| Attribute | Contents |
|---|---|
| `ctx.root` | The asset's top node |
| `ctx.subject` | The asset's name, type and task |
| `ctx.host` | The application |

## Settings

Put values a studio might want to change in `settings`:

```python
class UnitScale(Check):
    settings = {"tolerance": 0.000001}

    def validate(self, ctx):
        tolerance = self.settings["tolerance"]
        ...
```

A studio can change them in config without editing the check. A misspelled
setting name in config is reported as an error, not ignored.

## Fixes

Add a `fix` method and the **Fix** button (or `--fix`) will use it:

```python
    def validate(self, ctx):
        for obj in ctx.host.meshes(ctx.root):
            if tuple(obj.scale) != (1, 1, 1):
                yield self.issue(f"{obj.name} is scaled", obj)

    def fix(self, ctx, issues):
        for issue in issues:
            ctx.host.apply_scale(issue.targets)
```

After `fix` runs, the check runs again. It's reported as **fixed** if nothing
is left, and as failed (listing what's left) otherwise.

To pass extra information from `validate` to `fix`, add keyword arguments:
`self.issue("Wrong UV set", mesh, expected="map1")` puts it in
`issue.data["expected"]`.

## Config

```toml
# studio.toml
check_paths = ["checks"]          # relative to this file

[checks.UnitScale]
severity = "warning"
settings = { tolerance = 0.0001 }

[checks.RootNotEmpty]
enabled = false
```

Point `PUBLISH_VALIDATOR_CONFIG` at one or more of these files. Later files
win, so list the studio file first and project files after it:

```bash
export PUBLISH_VALIDATOR_CONFIG=/studio/validator.toml:/projects/foo/validator.toml
```

## Sharing work between checks

If several checks need the same expensive data, compute it once per run:

```python
meshes = ctx.cached("meshes", lambda: ctx.host.meshes(ctx.root))
```

## Pointing at faces, edges or vertices

```python
from publish_validator import Component

yield self.issue(f"{obj.name} has ngons", Component(obj, "face", ngon_indices))
```

In Blender, **Select** then goes into Edit Mode with exactly those faces
selected.

## Base classes

To share code between checks, make a base class and mark it `abstract` so it
isn't run on its own:

```python
class MeshCheck(Check):
    abstract = True
    hosts = ["blender"]

    def meshes(self, ctx):
        return ctx.host.meshes(ctx.root)
```

## Testing a check

Checks that only use the generic host methods can be tested with pytest,
without opening an application:

```python
from publish_validator import FAILED
from publish_validator.testing import FakeNode, run_check_on
from my_checks.hierarchy import HasGeoGroup


def test_missing_geo_group():
    root = FakeNode("chair", FakeNode("render"))
    assert run_check_on(HasGeoGroup, root).status == FAILED
```

`FakeNode` accepts any attribute (`FakeNode("cube", scale=(2, 1, 1))`).
Blender-only checks are best tested in Blender; see `tests/blender/run.py`.

To see what loads and where each check runs:

```bash
python -m publish_validator --list --path my_checks
```
