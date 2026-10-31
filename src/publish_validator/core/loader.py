"""Finding and loading check files.

Checks are plain .py files in folders. These folders are searched, in order:
the built-in checks that ship with this package, the check_paths from config,
and the folders listed in the PUBLISH_VALIDATOR_PATH environment variable.
"""

import ast
import importlib.util
import os
import sys
import traceback
from pathlib import Path

from .check import Check
from .results import LoadError

CHECK_PATH_ENV = "PUBLISH_VALIDATOR_PATH"
BUILTIN_CHECKS = Path(__file__).resolve().parent.parent / "checks"

# A folder with one of these names only loads inside that application.
HOST_FOLDERS = {"blender", "maya", "houdini"}

# Modules that only exist inside an application. A check file that needs one of
# them is skipped quietly elsewhere, instead of being reported as broken.
HOST_MODULES = {"bpy", "bmesh", "mathutils", "maya", "pymel", "hou"}

# Folders we added to sys.path so check files can import their helper files.
helper_folders = set()


def load_checks(folders=(), host_name=None):
    """Load every check class. Returns (checks, load_errors).

    host_name skips folders meant for other applications. None loads everything.
    """
    checks = {}
    errors = []
    forget_helper_modules()
    for folder in check_folders(folders):
        if not folder.is_dir():
            errors.append(LoadError(str(folder), "Check folder does not exist"))
            continue

        for path in find_check_files(folder, host_name):
            try:
                module = import_file(path)
            except Exception as error:
                if not needs_other_application(error):
                    errors.append(LoadError(str(path), traceback.format_exc()))
                continue

            for check in checks_in_module(module):
                name = check.__name__
                if name in checks:
                    errors.append(
                        LoadError(str(path), f"Two checks are called {name}. Rename one.")
                    )
                else:
                    checks[name] = check

    return list(checks.values()), errors


def check_folders(folders=()):
    """Every folder to search, in order and without duplicates."""
    env_folders = os.environ.get(CHECK_PATH_ENV, "").split(os.pathsep)
    found = []
    for folder in [BUILTIN_CHECKS, *folders, *env_folders]:
        if folder:
            folder = Path(folder).expanduser().resolve()
            if folder not in found:
                found.append(folder)
    return found


def class_names_on_disk(folders=()):
    """The names of every class in every check file, for every application.

    The files are read, not run, so this also finds checks for other applications
    (a Maya check while in Blender), which config is allowed to mention.
    """
    names = set()
    for folder in check_folders(folders):
        if not folder.is_dir():
            continue
        for path in find_check_files(folder):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue  # load_checks reports broken files
            names.update(node.name for node in tree.body if isinstance(node, ast.ClassDef))
    return names


def find_check_files(folder, host_name=None):
    files = []
    for path in sorted(folder.rglob("*.py")):
        parts = path.relative_to(folder).parts

        # _helpers.py, _private/ and .hidden/ are not check files.
        if any(part.startswith(("_", ".")) for part in parts):
            continue

        # blender/ only loads in Blender, maya/ only in Maya, and so on.
        folder_names = parts[:-1]
        if host_name and any(n in HOST_FOLDERS and n != host_name for n in folder_names):
            continue

        files.append(path)
    return files


def import_file(path):
    """Run a .py file as a fresh module, so edited files are picked up on every load."""
    # Let the file import helper files (like _utils.py) from its own folder.
    # Appended rather than inserted, so a check file can never hide a real module.
    folder = str(path.parent)
    if folder not in sys.path:
        sys.path.append(folder)
        helper_folders.add(folder)

    name = f"publish_validator_checks.{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # some tools (dataclasses, pickle) expect this
    spec.loader.exec_module(module)
    return module


def forget_helper_modules():
    """Forget helper files imported by checks, so edits to them are picked up on reload."""
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if file and str(Path(file).parent) in helper_folders:
            del sys.modules[name]


def checks_in_module(module):
    """The Check classes defined in a file (not ones it imported from elsewhere)."""
    found = []
    for value in vars(module).values():
        if not (isinstance(value, type) and issubclass(value, Check)):
            continue
        if value is Check or value.__module__ != module.__name__:
            continue
        if value.__dict__.get("abstract") or value in found:
            continue
        found.append(value)
    return found


def needs_other_application(error):
    """True if the error is just "bpy/maya/hou isn't available here"."""
    if isinstance(error, ModuleNotFoundError) and error.name:
        return error.name.split(".")[0] in HOST_MODULES
    return False
