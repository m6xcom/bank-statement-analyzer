"""Turn a Report into the text the user sees."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from analyzer.analysis import (
    CategoryTotal,
    Classified,
    Direction,
    DuplicateGroup,
    EmptyReason,
    Report,
)
from analyzer.models import NO_VALUE, RejectedRow

NO_OPERATIONS = "Statement contains no operations"
EMPTY_MESSAGES = {
    EmptyReason.FILTERED_OUT: "No operations left after filters",
    EmptyReason.NOTHING_COUNTED: "No operations were counted",
}


def money(value: Decimal) -> str:
    """Two decimal places, half-up, never "-0.00"."""
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)
    return format(rounded, "f")


def percent(value: Decimal) -> str:
    """One decimal place, half-up."""
    return format(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")


def _day(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _moment(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M:%S")


def _lines(numbers: tuple[int, ...]) -> str:
    return ", ".join(str(number) for number in numbers)


def _category_section(title: str, totals: list[CategoryTotal]) -> list[str]:
    rows = [title, f"  {'Category':<24} {'Amount, UAH':>14} {'Share':>7} {'Operations':>10}"]
    for total in totals:
        rows.append(
            f"  {total.category:<24} {money(total.amount):>14} "
            f"{percent(total.share):>6}% {total.count:>10}"
        )
    return rows


def _signed_counted_amount(item: Classified) -> Decimal:
    amount = item.operation.counted_amount
    return amount if item.operation.is_income else -amount


def _uncategorized_line(item: Classified) -> str:
    operation = item.operation
    return (
        f"  {_moment(operation.timestamp)}  {operation.description}  "
        f"{money(_signed_counted_amount(item))}  {operation.mcc or NO_VALUE}  "
        f"{item.uncategorized_reason}"
    )


def _excluded_line(item: Classified) -> str:
    operation = item.operation
    return (
        f"  {_moment(operation.timestamp)}  {operation.description}  "
        f"{money(operation.amount)}  {item.excluded_reason}"
    )


def _warning_line(group: DuplicateGroup) -> str:
    if group.confirmed:
        return (
            f"  Duplicate: lines {_lines(group.lines)} are the same operation "
            "exported more than once, counted once"
        )
    return (
        f"  Possible duplicate: lines {_lines(group.lines)} match in all columns "
        "but Balance is empty, counted every time"
    )


def _rejected_line(row: RejectedRow) -> str:
    reasons = []
    for issue in row.issues:
        if issue.column is None:
            reasons.append(issue.problem)
        else:
            reasons.append(f'column "{issue.column}" value "{issue.value}": {issue.problem}')
    return f"  Line {row.line}: " + "; ".join(reasons)


def _summary(report: Report, period: tuple[date, date]) -> list[str]:
    """Period and the totals of the shown side only."""
    start, end = period
    rows = [f"Period: {_day(start)} - {_day(end)}"]
    if report.shown in (None, Direction.EXPENSE):
        rows.append(f"Total expenses: {money(report.total_expenses)} UAH")
    if report.shown in (None, Direction.INCOME):
        rows.append(f"Total income: {money(report.total_income)} UAH")
    if report.shown is None:
        rows.append(f"Net: {money(report.net)} UAH")
    return rows


def render_report(report: Report) -> str:
    """Render all non-empty sections in the order SPEC.md defines."""
    sections: list[list[str]] = []

    if report.empty_reason is not None:
        sections.append([EMPTY_MESSAGES[report.empty_reason]])
    elif report.period is not None:
        sections.append(_summary(report, report.period))
    if report.expenses:
        sections.append(_category_section("Expenses by category", report.expenses))
    if report.income:
        sections.append(_category_section("Income by category", report.income))
    if report.uncategorized:
        sections.append(
            ["Uncategorized operations"] + [_uncategorized_line(i) for i in report.uncategorized]
        )
    if report.excluded:
        sections.append(["Excluded operations"] + [_excluded_line(i) for i in report.excluded])
    if report.duplicates:
        sections.append(["Warnings"] + [_warning_line(g) for g in report.duplicates])
    if report.rejected:
        sections.append(["Rejected rows"] + [_rejected_line(r) for r in report.rejected])

    return "\n\n".join("\n".join(section) for section in sections) + "\n"
