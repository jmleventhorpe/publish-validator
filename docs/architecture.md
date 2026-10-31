# Architecture

How the pieces of Publish Validator connect: what happens once when the
validator starts, what happens on every Validate click, and which code is
allowed to talk to Blender, Maya or Houdini.

## Starting up: config and checks

Creating a `Validator` reads the studio config and loads every check file once.
Anything that goes wrong here is collected as a loading problem, not raised, so
one bad file never stops the others.

```mermaid
flowchart LR
    files["Config files (TOML)<br/>studio.toml, project.toml"]
    folders["Check folders<br/>checks/ (built in)<br/>check_paths<br/>PUBLISH_VALIDATOR_PATH"]
    config["load_config()<br/>core/config.py"]
    loader["load_checks()<br/>core/loader.py"]
    validator["Validator(host)<br/>core/validator.py"]
    problems["Loading problems<br/>broken files, duplicate names,<br/>config mistakes"]

    files -- "read in order, later wins" --> config
    config -- "check_paths" --> loader
    folders -- ".py files" --> loader
    config -- "Config: resolver, check options" --> validator
    loader -- "check classes + errors" --> validator
    validator -- "load_errors" --> problems
```

- The config decides where checks come from (`check_paths`) and how the asset
  is found (`resolver`).
- Loading problems are shown in the Blender panel and included in every report.

## One click of Validate

Every run follows the same four steps inside `Validator.run()`. The panel and
the command line only start it and show what comes back.

```mermaid
sequenceDiagram
    participant UI as Panel or CLI
    participant V as Validator
    participant R as PropertyResolver
    participant C as Check
    participant H as BlenderHost

    UI->>V: run()
    Note over V: 1. resolve()
    V->>R: resolve(host)
    R->>H: selection(), parent(), get_property()
    R-->>V: Subject
    Note over V: 2. checks_for(subject)
    V->>C: applies_to(host name, subject)
    C-->>V: true or false
    Note over V: 3. run_check() for each check that applies
    loop each check
        V->>C: validate(ctx)
        C->>H: scene queries through ctx.host
        C-->>V: Issues
        opt Fix was pressed
            V->>C: fix(ctx, issues)
            V->>C: validate(ctx) again
            C-->>V: Issues still left
        end
    end
    Note over V: 4. build the Report
    V-->>UI: Report
```

- **Each check runs inside its own safety net.** If a check crashes, it's
  reported as `errored` and the loop carries on with the next one.
- **Step 3 reads each check's config** (`enabled`, `severity`, `settings`)
  before running it.
- **After a fix, the check runs again**, so the report shows what is really
  left rather than assuming the fix worked.

## Who may talk to the application

The core never imports `bpy`, `maya` or `hou`. Applications plug in underneath
it by subclassing `Host`, and checks plug in on top by subclassing `Check`.

```mermaid
flowchart TB
    subgraph checks["Check files"]
        blenderChecks["checks/blender/<br/>UnitScale, AllowedObjectTypes"]
        genericChecks["checks/generic/<br/>RootNotEmpty"]
        studioChecks["Studio folders<br/>check_paths, PUBLISH_VALIDATOR_PATH"]
    end

    subgraph core["core/ - pure Python, no bpy, maya or hou"]
        coreFiles["check.py, validator.py, loader.py, config.py<br/>subject.py, host.py, results.py"]
    end

    subgraph hosts["Host adapters"]
        blenderHost["hosts/blender/<br/>BlenderHost and the panel<br/>tested in Blender 5.2"]
        mayaHost["hosts/maya/<br/>MayaHost<br/>not yet tested in Maya"]
        houdiniHost["hosts/houdini/<br/>HoudiniHost<br/>not yet tested in Houdini"]
    end

    checks -- "subclass Check" --> core
    hosts -- "subclass Host" --> core
    blenderChecks -. "Blender helpers, e.g. meshes()" .-> blenderHost
```

- A check limited to `hosts = ["blender"]` may use `BlenderHost` helpers such
  as `meshes()`. A check with no `hosts` sticks to the generic `Host` methods,
  so it runs in every application.
- Supporting a new application means one new folder under `hosts/`.

## Which file does what

| File | Job | Used by |
|---|---|---|
| `core/check.py` | `Check` base class (metadata, settings, `validate`, `fix`) and `Context` | Every check file, `run_check` |
| `core/validator.py` | `Validator`: loads everything, runs checks, builds the report | Panel, command line, publish hooks |
| `core/loader.py` | Finds and imports check files, applying the folder rules | `Validator.reload()` |
| `core/config.py` | Reads and merges the TOML config files | `Validator` |
| `core/subject.py` | `Subject` (the asset) and `PropertyResolver` | `Validator.resolve()` |
| `core/host.py` | `Host` base class: the methods every application must provide | Each host adapter |
| `core/results.py` | `Issue`, `CheckResult`, `Report`, with text and JSON output | Everything that shows results |
| `hosts/blender/` | `BlenderHost` and the sidebar panel | Blender |
| `cli.py` | Command line: `--root`, `--all`, `--fix`, `--json`, `--list` | Headless runs, the farm |
| `testing.py` | `FakeNode`, `FakeHost`, `run_check_on` | Tests for checks, without an application |
