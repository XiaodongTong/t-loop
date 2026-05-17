"""tloop archive — view archived task runs."""

import config
from state import show_archives


def add_parser(subparsers):
    p = subparsers.add_parser("archive", help="View archived task runs")
    p.add_argument("--latest", action="store_true", help="Show most recent archive details")
    p.set_defaults(func=handle)


def handle(args):
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    show_archives(latest=args.latest)
