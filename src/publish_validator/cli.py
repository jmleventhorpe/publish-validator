"""Run the validator from the command line, without a UI.

Validating needs a scene, so run it inside the application:

    blender -b scene.blend --python-exit-code 1 \
        --python-expr "import sys; from publish_validator.cli import main; sys.exit(main())" \
        -- --all

Outside an application, only --list works:

    python -m publish_validator --list

Exit code: 0 if nothing blocks the publish, 1 if something does, 2 for usage errors.
"""

import argparse
import sys

from .core.config import ConfigError, load_config
from .core.loader import load_checks
from .core.subject import ResolveError
from .core.validator import Validator


def main(args=None):
    if args is None:
        # Blender passes our arguments after "--".
        args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]

    parser = argparse.ArgumentParser(prog="publish-validator")
    parser.add_argument("--root", help="name of the asset root to validate")
    parser.add_argument("--all", action="store_true", help="validate every asset in the scene")
    parser.add_argument("--fix", action="store_true", help="apply automatic fixes")
    parser.add_argument("--only", nargs="+", metavar="CHECK", help="run only these checks")
    parser.add_argument("--config", nargs="+", default=[], help="extra config files")
    parser.add_argument("--path", nargs="+", default=[], help="extra check folders")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--list", action="store_true", help="list the available checks")
    parser.add_argument("--verbose", action="store_true", help="also show checks that passed")
    options = parser.parse_args(args)

    try:
        config = load_config(options.config)
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 2

    if options.list:
        list_checks(config.check_paths + options.path)
        return 0

    from .hosts import current_host

    try:
        host = current_host()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 2

    try:
        validator = Validator(host, config, check_paths=options.path)
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 2

    if options.only:
        known = [check.__name__ for check in validator.checks]
        for name in options.only:
            if name not in known:
                print(f"Warning: there is no check called {name}.", file=sys.stderr)

    try:
        if options.all:
            reports = validator.run_all(options.fix, options.only)
        else:
            node = None
            if options.root:
                node = host.find(options.root)
                if node is None:
                    print(f"Nothing called {options.root} in the scene.", file=sys.stderr)
                    return 2
            reports = [validator.run(validator.resolve(node), options.fix, options.only)]
    except ResolveError as error:
        print(f"{error} On the command line, use --root NAME or --all.", file=sys.stderr)
        return 2

    if not reports:
        print("No assets found in the scene.", file=sys.stderr)
        return 2

    for report in reports:
        print(report.as_json() if options.json else report.as_text(show_passed=options.verbose))
    return 0 if all(report.passed for report in reports) else 1


def list_checks(folders):
    checks, errors = load_checks(folders)
    for check in sorted(checks, key=lambda c: (c.category, c.__name__)):
        where = ", ".join(check.hosts) if check.hosts else "any host"
        tasks = ", ".join(check.tasks) if check.tasks else "any task"
        fix = "  (can fix)" if check.can_fix() else ""
        print(f"{check.__name__:<24} {check.category:<12} {where} / {tasks}{fix}")
    for error in errors:
        print(f"Could not load {error.source}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
