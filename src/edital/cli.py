"""Standalone command dispatch without importing the TUI for maintenance commands."""

import argparse
import sys
from collections.abc import Sequence

from .editor import Edital


def main(argv: Sequence[str] | None = None) -> int:
    """Run file editing, configuration editing, or recovery maintenance.

    Returns zero on success, one for operational errors. Invalid options are
    reported by argparse with exit status two. ``--`` escapes command names.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="edital", description="Multi-tab terminal text editor",
                                     epilog="Commands: conf; cache list; cache purge. Use -- before reserved filenames.")
    parser.add_argument("paths", nargs="*", metavar="PATH", help="Existing files or new named drafts")
    parser.add_argument("-R", "--recover", action="store_true", help="Restore unsaved recovery snapshots")
    parser.add_argument("--no-cache", action="store_true", help="Disable configured restoration and caching for this session")
    parser.add_argument("--auto-save", type=int, metavar="MS", help="Periodic autosave interval; 0 disables it")
    parser.add_argument("--no-prompt", action="store_true", help="Discard without confirmation when not caching")
    command = None
    if arguments and arguments[0] in ("conf", "cache"):
        command = arguments.pop(0)
        if command == "cache":
            maintenance = argparse.ArgumentParser(prog="edital cache", description="Manage recovery snapshots")
            maintenance.add_argument("operation", choices=("list", "purge"))
            operation = maintenance.parse_args(arguments).operation
        else:
            configuration = argparse.ArgumentParser(prog="edital conf", description="Edit user configuration; restart to apply")
            configuration.parse_args(arguments)
    else:
        options = parser.parse_intermixed_args(arguments)
        if options.recover and options.no_cache:
            parser.error("--recover and --no-cache cannot be used together")
        if options.auto_save is not None and options.auto_save < 0:
            parser.error("--auto-save must be a nonnegative integer in milliseconds")
    overrides = {}
    if command is None:
        if options.no_cache:
            overrides["cache"] = False
            overrides["auto_restore"] = False
        if options.recover:
            overrides["auto_restore"] = True
        if options.no_prompt:
            overrides["prompt"] = False
        if options.auto_save is not None:
            overrides["auto_save"] = options.auto_save
    elif command == "conf":
        overrides["auto_restore"] = False
    try:
        editor = Edital(**overrides)
        if command == "cache":
            if operation == "purge":
                editor.clear_cache()
            else:
                for entry in editor.cache:
                    print(f"{entry.id}\t{entry.path or 'draft'}\t{entry.size} bytes")
            return 0
        if command == "conf":
            editor.open(editor.conf.path)
        else:
            editor.open(*options.paths)
        editor.run(create_draft=command is None)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"edital: {error}", file=sys.stderr)
        return 1
    return 0
