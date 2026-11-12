"""Command-line interface: `python -m analyzer report FILE ...`."""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from analyzer.analysis import Direction, Filters, build_report
from analyzer.loading import DEFAULT_RULES_PATH, InputError, load_rules, load_statement
from analyzer.render import NO_OPERATIONS, render_report

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_USAGE = 2


def _iso_date(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {text!r}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m analyzer",
        description="Break down a Monobank statement by category.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    report = commands.add_parser("report", help="print the report for a statement")
    report.add_argument("file", metavar="FILE", type=Path, help="statement CSV file")
    report.add_argument(
        "--rules",
        metavar="PATH",
        type=Path,
        default=DEFAULT_RULES_PATH,
        help="rules file (default: rules.json in the project root)",
    )
    report.add_argument(
        "--from", dest="date_from", metavar="YYYY-MM-DD", type=_iso_date,
        help="include operations on or after this date",
    )
    report.add_argument(
        "--to", dest="date_to", metavar="YYYY-MM-DD", type=_iso_date,
        help="include operations on or before this date",
    )
    report.add_argument("--category", metavar="NAME", help="show only this category")
    direction = report.add_mutually_exclusive_group()
    direction.add_argument(
        "--only-income", action="store_true", help="count only income"
    )
    direction.add_argument(
        "--only-expenses", action="store_true", help="count only expenses"
    )
    return parser


def _parse_args(argv: list[str] | None) -> tuple[argparse.Namespace, Filters]:
    """Parse arguments; raises SystemExit on argument errors (argparse style)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    date_from: date | None = args.date_from
    date_to: date | None = args.date_to
    if date_from is not None and date_to is not None and date_from > date_to:
        parser.error("--from must not be later than --to")

    direction: Direction | None = None
    if args.only_income:
        direction = Direction.INCOME
    elif args.only_expenses:
        direction = Direction.EXPENSE
    filters = Filters(
        date_from=date_from,
        date_to=date_to,
        category=args.category,
        direction=direction,
    )
    return args, filters


def _exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return EXIT_OK
    if isinstance(exc.code, int):
        return exc.code
    return EXIT_USAGE


def _input_error(exc: InputError) -> int:
    logger.info("stopped with an input error")
    sys.stderr.write(f"error: {exc}\n")
    return EXIT_INPUT_ERROR


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return the exit code. Never raises SystemExit."""
    try:
        args, filters = _parse_args(argv)
    except SystemExit as exc:
        return _exit_code(exc)

    try:
        rules = load_rules(args.rules)
    except InputError as exc:
        return _input_error(exc)

    if filters.category is not None and filters.category not in rules.category_names:
        logger.info("stopped: unknown --category")
        available = ", ".join(rules.category_names)
        sys.stderr.write(f'Unknown category "{filters.category}". Available: {available}\n')
        return EXIT_USAGE

    try:
        statement = load_statement(args.file)
    except InputError as exc:
        return _input_error(exc)

    if statement.row_count == 0:
        sys.stdout.write(NO_OPERATIONS + "\n")
        return EXIT_OK

    report = build_report(statement.operations, statement.rejected, rules, filters)
    sys.stdout.write(render_report(report))
    return EXIT_OK
