"""tloop run — execute tasks defined in ~/.tloop/tasks.yaml."""

import sys

import config
from config import ensure_tloop_home, load_config
from state import load_state, save_state, show_status, archive_completed_tasks
from task import run_task


def add_parser(subparsers):
    p = subparsers.add_parser("run", help="Run tasks defined in ~/.tloop/tasks.yaml")
    p.add_argument("--status", "-s", action="store_true", help="Show task status")
    p.add_argument("--reset", action="store_true", help="Reset all tasks to pending")
    p.add_argument("--only", type=int, help="Run only task #N (1-based)")
    p.add_argument("--confirm", "-i", action="store_true", help="Confirm before each task")
    p.add_argument("--continue", "-c", dest="continue_on_fail", action="store_true",
                    help="Continue even if a task fails")
    p.set_defaults(func=handle)


def handle(args):
    ensure_tloop_home()

    cfg = load_config()
    tasks = cfg.get("tasks", [])

    if not tasks:
        print("No tasks defined in tasks.yaml")
        sys.exit(0)

    state = load_state()

    if args.status:
        show_status(tasks, state)
        return

    if args.reset:
        state = {"tasks": {}, "version": 1}
        save_state(state)
        print(f"{config.GREEN}State reset. All tasks are pending.{config.RESET}")
        return

    if args.only is not None:
        if args.only < 1 or args.only > len(tasks):
            print(f"{config.RED}Invalid task number: {args.only}{config.RESET}")
            sys.exit(1)
        indices = [args.only - 1]
    else:
        indices = list(range(len(tasks)))

    ran_any = False
    for i in indices:
        ts = state.get("tasks", {}).get(str(i), {})
        status = ts.get("status", "pending")

        if status == "done" and args.only is None:
            print(f"⏭️  Task [{i + 1}] already done, skipping")
            continue

        if args.confirm:
            name = tasks[i].get("name", f"Task {i + 1}")
            try:
                resp = input(f"\nRun task [{i + 1}] '{name}'? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                break
            if resp.lower() != "y":
                print("Skipped.")
                continue

        ran_any = True
        success = run_task(tasks[i], i, state)
        if not success and not args.continue_on_fail:
            print(f"\n{config.YELLOW}Stopped. Use -c to continue after failures.{config.RESET}")
            break

    if ran_any:
        print(f"\n{config.BOLD}--- Final Status ---{config.RESET}")
        show_status(tasks, state)

    archive_completed_tasks(cfg, state)
