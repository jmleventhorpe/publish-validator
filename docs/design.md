# Design notes

Why Publish Validator is built the way it is. For how the pieces connect, see
[architecture.md](architecture.md); for writing checks, see
[writing-checks.md](writing-checks.md).

## Goals

1. **Adding a check should take minutes.** A check is one small class in a
   plain `.py` file. No registration, no framework to learn.
2. **Studios change behaviour without editing code.** Turning checks off,
   changing severities and tuning settings all happen in TOML config.
3. **The same rules run with and without a UI.** Artists use the panel; a
   publish hook or farm job runs the same checks from the command line, and its
   exit code decides whether the publish goes ahead.
4. **One core for every application.** Blender first, Maya and Houdini next,
   without rewriting the checks' surroundings for each.

## Decisions

### A core that never imports an application

`core/` holds the check base class, the loader, config, results and the
`Validator`, and none of it imports `bpy`, `maya` or `hou`. Everything
application-specific sits behind a small `Host` class (selection, parents,
children, custom properties, select). That keeps the core testable with plain
`pytest` and fake scenes, and means supporting a new application is one new
folder under `hosts/`.

### Checks are declarative classes, found by folder

A check declares where it applies (`hosts`, `tasks`, `asset_types`), its
`category`, `severity` and tunable `settings`, and implements `validate()`.
The docstring is its documentation and doubles as the tooltip in the panel.
Checks are identified by class name, which is what config files refer to.

Checks are found by scanning folders (built-in, from config, and from an
environment variable), the way most VFX tools load plugins, rather than through
pip entry points, which are awkward inside an application's bundled Python.
A folder named after an application only loads in that application, and a file
that fails because `bpy` isn't available is skipped quietly elsewhere. Any other
error becomes a visible "loading problem" instead of stopping the other checks
from loading.

### Issues, not log strings

`validate()` yields `Issue` objects: a message, the objects involved, and an
optional severity. Because results are data rather than formatted text, the same
report can drive the panel, plain-text output and JSON. Each issue also carries
its targets, so **Select** works for every check without extra code. Geometry
checks go one step further and point at exact faces, edges or vertices, so
Select can drop straight into Edit Mode on the problem.

### Fail safely

Every check runs inside its own error handling. A check that crashes is shown as
*errored*, with its traceback, and the rest still run. After a fix, the check
runs again, so the report shows what is actually left instead of assuming the fix
worked.

### Report first, fix where it's safe

Most checks only report. A fix exists only where it is mechanical and keeps the
model looking the same, such as baking scale into the mesh. Geometry clean-up,
like merging vertices or applying modifiers, changes the artist's work and is left
to them.

### Config is validated against the checks

Config is layered: a studio file, then project files, with later files winning
per setting. When the checks load, the config is checked against them, so a
misspelled check name, an unknown setting, or a value of the wrong type
(`tolerance = "0.1"`) shows up straight away as a loading problem rather than
being silently ignored.

### A native Blender panel, not Qt

Qt was the obvious way to share one UI across Blender and Maya, but Blender
doesn't ship it. The main library for running Qt inside Blender has no Linux
support, and on Wayland a Qt window can't be attached to Blender's window.
Blender also can't host a clean custom window from Python, and pop-ups close when
the mouse leaves. So the Blender UI is a sidebar panel, built from Blender's own
widgets.

The panel holds no validation logic: it calls the `Validator` and draws the
`Report`. A Maya UI can be a different drawing of the same data.

### Artists can skip checks; the publish can't

The panel lets artists untick checks while they work. That only affects the
panel: a headless publish always runs every check the studio has enabled.
Skipping is a convenience, not a loophole.

### Results that can't go stale silently

After validating, the panel stores a cheap fingerprint of the asset: names,
transforms, modifiers and vertex positions. If the asset changes, the panel says
the results are out of date. Selecting things doesn't change the fingerprint, and
neither do the tool's own fixes, which re-validate anyway.

### Names that survive USD

The default naming convention uses only letters, digits and underscores, since
USD prim names allow nothing else. It uses an optional `L_`/`R_`/`C_` side
prefix, and no `.001` endings. It has no `_GEO` or `_GRP` suffixes, because
Blender's outliner already shows what each object is. Proxies end in `_proxy` and
live under the `proxy` group, matching the `geo` → `render`/`proxy` layout from
the USD asset-structure guidelines. Every part of the convention is a setting.

### Python 3.11

The code sticks to Python 3.11 syntax so it runs in Maya 2026, and is tested on
3.13, which Blender 5.1 and later use. The core has no third-party
dependencies.

## Known limitations

- The Maya and Houdini host adapters are written but not yet tested in those
  applications, and there is no Maya or Houdini UI yet.
- The sidebar is narrow by default; long messages wrap, and widening it helps.
- A category that passes everything starts closed only the first time it
  appears; after that Blender remembers whether you left it open.
