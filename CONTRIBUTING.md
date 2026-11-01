# Contributing

Thanks for helping out. The most common contribution is a new check, so that
comes first.

## Adding a check

1. **Pick the folder.** Built-in checks live in
   `src/publish_validator/checks/`. Use `generic/` if the check only needs the
   generic host methods (it then runs in every application), or `blender/` if it
   needs Blender. Put it in the file for its category (`structure.py`,
   `naming.py`, `transforms.py`, `geometry.py`).
2. **Write the class.** A docstring saying what the rule is, why it matters
   and how to fix it by hand; `category`, `hosts` and `tasks`; anything tunable
   in `settings`; and a `validate()` that yields one issue per problem.
   [docs/writing-checks.md](docs/writing-checks.md) covers everything a check
   can do.
3. **Report, don't fix,** unless the fix is mechanical and keeps the model
   looking the same (like baking scale into the mesh).
4. **Test it.** Generic checks can be tested with plain pytest using
   `publish_validator.testing`. Blender checks get a case in
   `tests/blender/run.py`: the clean asset must still pass everything, and your
   check must find its problem.
5. **List it** in the "Built-in checks" table in the README.

Studio-specific rules usually belong in your own check folder rather than in
this repo: see the example in `examples/studio_checks/`.

## Development setup

You need [uv](https://docs.astral.sh/uv/) and Blender 4.2 or newer.

```bash
uv run --python 3.11 --group dev pytest   # core tests (please run with 3.13 too)
uv run --group dev ruff check             # lint
uv run --group dev ruff format            # format
blender -b --factory-startup --python-exit-code 1 --python tests/blender/run.py
blender --python scripts/blender_demo.py  # try the panel on a demo asset
```

## Style

- Python 3.11 syntax: the code has to run in Maya 2026.
- No third-party dependencies in `core/`, and no `bpy`, `maya` or `hou` imports
  there either.
- Plain, readable code over clever code. Comments explain why, not what.
- Messages are written for artists: say what is wrong and with which object.

## Pull requests

Keep each pull request to one change, describe what it does and how you tested
it, and make sure lint and both test suites pass.
