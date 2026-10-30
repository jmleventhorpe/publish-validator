"""Blender extension wrapper for Publish Validator.

The package itself ships as a wheel listed in blender_manifest.toml, which
Blender installs for this extension. For development, put the repository's
``src`` folder on PYTHONPATH before starting Blender instead of building.
"""


def register():
    from publish_validator.hosts.blender import register as _register

    _register()


def unregister():
    from publish_validator.hosts.blender import unregister as _unregister

    _unregister()
