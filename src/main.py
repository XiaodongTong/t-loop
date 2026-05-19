"""t-loop entry point."""

import argparse

__version__ = "0.4.0"


def main():
    parser = argparse.ArgumentParser(
        prog="tloop",
        description="t-loop: Automated Claude Code task runner",
        epilog="Tip: place project-level AI instructions in ./docs/tloop/constitution.md — tloop will auto-load them as constitutional rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version",
                        version=f"tloop {__version__}")

    subparsers = parser.add_subparsers(title="commands")

    from cmd_run import add_parser as add_run
    from cmd_edit import add_parser as add_edit
    from cmd_migrate import add_parser as add_migrate
    from cmd_archive import add_parser as add_archive

    add_run(subparsers)
    add_edit(subparsers)
    add_migrate(subparsers)
    add_archive(subparsers)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
