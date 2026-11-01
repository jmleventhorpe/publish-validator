# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-01

First release.

### Added

- **Core:** check base class, folder-based check loading, layered TOML config
  that is validated against the checks, a `Validator` that runs checks with
  per-check error handling and re-checks after fixing, and text and JSON
  reports.
- **Blender panel:** checks grouped by category with green, orange and red
  status icons; tick or untick checks for the session; a Details box with each
  check's description and problems; per-check Fix and Select; Fix All; and a
  warning when the asset changes after validating.
- **16 built-in checks** across Structure, Naming, Transforms and Geometry.
  Geometry checks point at the exact faces, edges or vertices.
- **Command line** for headless runs and publish hooks, with exit codes and
  JSON output.
- **Blender extension** build script, a demo scene and an example studio
  check folder.
- **Maya and Houdini host adapters,** written but not yet tested in those
  applications.

[0.1.0]: https://github.com/jmleventhorpe/publish-validator/releases/tag/v0.1.0
