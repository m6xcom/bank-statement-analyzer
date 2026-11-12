"""Read the statement CSV and the rules JSON into validated models."""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from analyzer.models import REQUIRED_COLUMNS, Operation, RejectedRow, RowIssue, Rules

logger = logging.getLogger(__name__)

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "rules.json"


class InputError(Exception):
    """A file or data error that stops the report (exit code 1)."""


@dataclass(frozen=True)
class Statement:
    """Result of reading a statement file."""

    row_count: int
    operations: list[Operation]
    rejected: list[RejectedRow]


def load_rules(path: Path) -> Rules:
    """Load and validate the rules file. Errors name the full path."""
    full_path = path.absolute()
    try:
        text = full_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InputError(f"Rules file not found: {full_path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"Cannot read rules file {full_path}: {exc}") from exc

    try:
        return Rules.model_validate_json(text)
    except ValidationError as exc:
        raise InputError(_describe_rules_error(full_path, exc)) from exc


def _describe_rules_error(path: Path, exc: ValidationError) -> str:
    problems: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        if error["type"] == "json_invalid":
            problems.append("not valid JSON")
        elif error["type"] == "missing":
            problems.append(f"missing required key '{location}'")
        elif location:
            problems.append(f"invalid value at '{location}': {_error_message(error['msg'])}")
        else:
            problems.append(_error_message(error["msg"]))
    return f"Invalid rules file {path}: " + "; ".join(problems)


def load_statement(path: Path) -> Statement:
    """Read a Monobank CSV statement and split rows into valid and rejected."""
    if path.suffix.lower() != ".csv":
        raise InputError(f"Statement must be a .csv file: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            return _parse_rows(path, file)
    except FileNotFoundError as exc:
        raise InputError(f"Statement file not found: {path}") from exc
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise InputError(f"Cannot read statement file {path}: {exc}") from exc


def _parse_rows(path: Path, file: TextIO) -> Statement:
    reader = csv.reader(file)
    header = next(reader, None)
    if header is None:
        logger.info("statement is empty")
        return Statement(row_count=0, operations=[], rejected=[])

    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        names = ", ".join(f'"{column}"' for column in missing)
        raise InputError(f"Statement {path} is missing required column(s): {names}")
    index = {column: header.index(column) for column in REQUIRED_COLUMNS}

    operations: list[Operation] = []
    rejected: list[RejectedRow] = []
    row_count = 0
    line = reader.line_num
    for cells in reader:
        row_line = line + 1
        line = reader.line_num
        if all(cell == "" for cell in cells):
            # Empty line: not an operation, but it still counts as a line.
            continue
        row_count += 1
        result = _parse_row(row_line, cells, header, index)
        if isinstance(result, RejectedRow):
            for issue in result.issues:
                # Only the line number, column and problem: never cell contents.
                logger.info(
                    "line %d rejected: %s%s",
                    row_line,
                    f"{issue.column}: " if issue.column else "",
                    issue.problem,
                )
            rejected.append(result)
        else:
            operations.append(result)

    logger.info(
        "read %d rows: %d valid, %d rejected", row_count, len(operations), len(rejected)
    )
    return Statement(row_count=row_count, operations=operations, rejected=rejected)


def _parse_row(
    line: int, cells: list[str], header: list[str], index: dict[str, int]
) -> Operation | RejectedRow:
    if len(cells) != len(header):
        problem = f"expected {len(header)} fields, found {len(cells)}"
        return RejectedRow(
            line=line, issues=(RowIssue(column=None, value=None, problem=problem),)
        )

    data: dict[str, object] = {column: cells[i] for column, i in index.items()}
    data["line"] = line
    data["cells"] = tuple(cells)
    try:
        return Operation.model_validate(data)
    except ValidationError as exc:
        issues = tuple(
            RowIssue(
                column=str(error["loc"][0]) if error["loc"] else None,
                value=error["input"] if isinstance(error["input"], str) else None,
                problem=_error_message(error["msg"]),
            )
            for error in exc.errors()
        )
        return RejectedRow(line=line, issues=issues)


def _error_message(message: str) -> str:
    """Drop pydantic's "Value error, " prefix from validator messages."""
    prefix = "Value error, "
    return message[len(prefix):] if message.startswith(prefix) else message
