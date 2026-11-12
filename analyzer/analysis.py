"""Core logic: duplicates, categorization, filters and totals.

Works only with validated models from analyzer.models.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from analyzer.models import UNCATEGORIZED, Operation, RejectedRow, Rules

logger = logging.getLogger(__name__)


class Direction(Enum):
    EXPENSE = "expense"
    INCOME = "income"


@dataclass(frozen=True)
class Filters:
    """Command-line filters. None means "not set"."""

    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None
    direction: Direction | None = None

    @property
    def any_given(self) -> bool:
        return any(
            value is not None
            for value in (self.date_from, self.date_to, self.category, self.direction)
        )


@dataclass(frozen=True)
class Classified:
    """An operation after the categorization rules.

    `category` is None for an excluded operation: it has no category.
    """

    operation: Operation
    direction: Direction
    category: str | None
    excluded_reason: str | None
    uncategorized_reason: str | None


@dataclass(frozen=True)
class CategoryTotal:
    category: str
    amount: Decimal
    share: Decimal
    count: int


@dataclass(frozen=True)
class DuplicateGroup:
    lines: tuple[int, ...]
    confirmed: bool


class EmptyReason(Enum):
    """Why no operation was counted."""

    FILTERED_OUT = "filtered out"
    NOTHING_COUNTED = "nothing counted"


@dataclass(frozen=True)
class Report:
    period: tuple[date, date] | None
    empty_reason: EmptyReason | None
    shown: Direction | None
    total_expenses: Decimal
    total_income: Decimal
    expenses: list[CategoryTotal]
    income: list[CategoryTotal]
    uncategorized: list[Classified]
    excluded: list[Classified]
    duplicates: list[DuplicateGroup]
    rejected: list[RejectedRow]

    @property
    def net(self) -> Decimal:
        return self.total_income - self.total_expenses


def classify(operation: Operation, rules: Rules) -> Classified:
    """Apply the categorization rules in order; the first match decides."""
    direction = Direction.INCOME if operation.is_income else Direction.EXPENSE
    mcc = operation.mcc

    excluded_reason: str | None = None
    description = operation.description.casefold()
    if any(pattern.casefold() in description for pattern in rules.own_transfer_patterns):
        excluded_reason = "own transfer"
    elif operation.is_income and mcc is not None and mcc not in rules.income_mccs:
        excluded_reason = "refund"

    category: str | None = None
    uncategorized_reason: str | None = None
    if excluded_reason is None:
        category = rules.categories.get(mcc, UNCATEGORIZED) if mcc else UNCATEGORIZED
        if mcc is None:
            uncategorized_reason = "no MCC"
        elif mcc not in rules.categories:
            uncategorized_reason = f"MCC {mcc} not in rules"

    return Classified(
        operation=operation,
        direction=direction,
        category=category,
        excluded_reason=excluded_reason,
        uncategorized_reason=uncategorized_reason,
    )


def find_duplicates(operations: list[Operation]) -> list[DuplicateGroup]:
    """Group rows that match in every column.

    With a non-empty Balance the group is a confirmed duplicate; with an empty
    or "—" Balance it is only a possible duplicate.
    """
    groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    has_balance: dict[tuple[str, ...], bool] = {}
    for operation in operations:
        groups[operation.cells].append(operation.line)
        has_balance[operation.cells] = operation.has_balance
    result = [
        DuplicateGroup(lines=tuple(lines), confirmed=has_balance[cells])
        for cells, lines in groups.items()
        if len(lines) > 1
    ]
    for group in result:
        logger.info(
            "%s duplicate rows at lines %s",
            "confirmed" if group.confirmed else "possible",
            ", ".join(str(line) for line in group.lines),
        )
    return sorted(result, key=lambda group: group.lines[0])


def _passes(item: Classified, filters: Filters) -> bool:
    day = item.operation.timestamp.date()
    if filters.date_from is not None and day < filters.date_from:
        return False
    if filters.date_to is not None and day > filters.date_to:
        return False
    if filters.category is not None and item.category != filters.category:
        return False
    if filters.direction is not None and item.direction != filters.direction:
        return False
    return True


def _category_totals(items: list[Classified]) -> list[CategoryTotal]:
    sums: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        category = item.category or UNCATEGORIZED
        sums[category] += item.operation.counted_amount
        counts[category] += 1
    total = sum(sums.values(), Decimal("0"))
    totals = [
        CategoryTotal(
            category=category,
            amount=amount,
            share=(amount / total * 100) if total else Decimal("0"),
            count=counts[category],
        )
        for category, amount in sums.items()
    ]
    return sorted(totals, key=lambda t: (-t.amount, t.category.casefold(), t.category))


def build_report(
    operations: list[Operation],
    rejected: list[RejectedRow],
    rules: Rules,
    filters: Filters,
) -> Report:
    duplicates = find_duplicates(operations)
    later_copies = {
        line for group in duplicates if group.confirmed for line in group.lines[1:]
    }
    classified = [
        classify(operation, rules)
        for operation in operations
        if operation.line not in later_copies
    ]
    selected = [item for item in classified if _passes(item, filters)]
    selected_lines = {item.operation.line for item in selected}

    counted = [item for item in selected if item.excluded_reason is None]
    expenses = [item for item in counted if item.direction is Direction.EXPENSE]
    income = [item for item in counted if item.direction is Direction.INCOME]

    days = [item.operation.timestamp.date() for item in counted]
    empty_reason: EmptyReason | None = None
    if not counted:
        empty_reason = (
            EmptyReason.FILTERED_OUT if filters.any_given else EmptyReason.NOTHING_COUNTED
        )
    return Report(
        period=(min(days), max(days)) if days else None,
        empty_reason=empty_reason,
        shown=filters.direction,
        total_expenses=sum((i.operation.counted_amount for i in expenses), Decimal("0")),
        total_income=sum((i.operation.counted_amount for i in income), Decimal("0")),
        expenses=_category_totals(expenses),
        income=_category_totals(income),
        uncategorized=[item for item in counted if item.uncategorized_reason is not None],
        excluded=[item for item in selected if item.excluded_reason is not None],
        duplicates=[group for group in duplicates if group.lines[0] in selected_lines],
        rejected=rejected,
    )
