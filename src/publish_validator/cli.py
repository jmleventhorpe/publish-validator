"""Command line / headless entry point.

Outside a DCC only ``--list`` is useful. To validate, run it inside the host::

    blender -b scene.blend --python-exit-code 1 \
        --python-expr "import sys; from publish_validator.cli import main; sys.exit(main())" \
        -- --all

Exit code is 0 when nothing blocks a publish, 1 otherwise, 2 on usage errors.
Arguments after ``--`` are used when running inside Blender.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .core.config import ConfigError, load_config
from .core.registry import Registry
from .core.report import format_text, to_json
from .core.subject import ResolveError
from .core.validator import Validator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-validator", description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="auto", help="blender, maya, houdini or auto (default)")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--root", help="name of the asset root node to validate")
    target.add_argument("--all", action="store_true", help="validate every asset in the scene")
    parser.add_argument("--fix", action="store_true", help="apply automatic fixes, then re-check")
    parser.add_argument("--only", nargs="+", metavar="ID", help="run only these check ids")
    parser.add_argument("--config", nargs="+", default=[], metavar="TOML", help="extra config")
    parser.add_argument("--path", nargs="+", default=[], metavar="DIR", help="extra check folders")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    parser.add_argument("--list", action="store_true", help="list available checks and exit")
    parser.add_argument("--verbose", action="store_true", help="show passed checks and tracebacks")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Inside Blender, arguments after ``--`` are used."""
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = build_parser().parse_args(argv)
    code = _main(args)
    if _inside_host():
        # Blender/Maya keep running after a script returns; make the code visible.
        print(f"publish-validator exit code: {code}")
    return code


def _main(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.list:
        return _list(args, config)

    from .hosts import get_host

    try:
        host = get_host(args.host)
    except (RuntimeError, ValueError, ImportError) as exc:
        print(exc, file=sys.stderr)
        return 2

    validator = Validator(host, config=config, paths=args.path)
    try:
        if args.all:
            reports = validator.run_all(fix=args.fix, only=args.only)
            if not reports:
                print("No assets found in the scene.", file=sys.stderr)
                return 2
        else:
            node = None
            if args.root:
                node = host.find(args.root)
                if node is None:
                    print(f"No node named {args.root!r}.", file=sys.stderr)
                    return 2
            reports = [validator.run(validator.resolve(node), fix=args.fix, only=args.only)]
    except ResolveError as exc:
        print(exc, file=sys.stderr)
        return 2

    for report in reports:
        if args.json:
            print(to_json(report))
        else:
            print(format_text(report, show_passed=args.verbose, show_tracebacks=args.verbose))
            print()
    return 0 if all(r.passed for r in reports) else 1


def _list(args: argparse.Namespace, config) -> int:
    from .hosts import available_hosts

    hosts = available_hosts()
    host = hosts[0] if args.host == "auto" and hosts else None
    if args.host != "auto":
        host = args.host
    registry = Registry.discover([*config.check_paths, *args.path], host=host)
    for check in sorted(registry, key=lambda c: (c.category, c.id)):
        scope = "/".join(
            ",".join(sorted(s)) if s else "*" for s in (check.hosts, check.tasks, check.asset_types)
        )
        fix = "[fix]" if check.is_fixable() else ""
        print(f"{check.id:<40} {check.category:<14} {scope:<20} {fix:<6} {check.summary()}")
    for error in registry.errors:
        print(f"load error: {error.source}: {error.message}", file=sys.stderr)
    return 0


def _inside_host() -> bool:
    return any(name in sys.modules for name in ("bpy", "maya.cmds", "hou"))


if __name__ == "__main__":
    sys.exit(main())
