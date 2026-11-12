"""Validated models: the boundary between raw text and the core logic.

Raw CSV cells and rules JSON are validated here. Everything after this module
works only with these models.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

DATE_COLUMN: Final = "Date and time"
DESCRIPTION_COLUMN: Final = "Description"
MCC_COLUMN: Final = "MCC"
AMOUNT_COLUMN: Final = "Card currency amount, (UAH)"
OPERATION_AMOUNT_COLUMN: Final = "Operation amount"
OPERATION_CURRENCY_COLUMN: Final = "Operation currency"
EXCHANGE_RATE_COLUMN: Final = "Exchange rate"
COMMISSION_COLUMN: Final = "Commission, (UAH)"
CASHBACK_COLUMN: Final = "Cashback amount, (UAH)"
BALANCE_COLUMN: Final = "Balance"

REQUIRED_COLUMNS: tuple[str, ...] = (
    DATE_COLUMN,
    DESCRIPTION_COLUMN,
    MCC_COLUMN,
    AMOUNT_COLUMN,
    OPERATION_AMOUNT_COLUMN,
    OPERATION_CURRENCY_COLUMN,
    EXCHANGE_RATE_COLUMN,
    COMMISSION_COLUMN,
    CASHBACK_COLUMN,
    BALANCE_COLUMN,
)

UNCATEGORIZED: Final = "uncategorized"

# Monobank writes an em dash (U+2014) when a value is absent.
NO_VALUE = "—"

_DATE_FORMAT = "%d.%m.%Y %H:%M:%S"
_DATE_PATTERN = re.compile(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}")
_NUMBER_PATTERN = re.compile(r"[+-]?\d+(\.\d+)?")
_SHORT_MCC_PATTERN = re.compile(r"\d{1,4}")


def _parse_money(value: object) -> Decimal:
    """Parse a money cell into Decimal, straight from the string."""
    if not isinstance(value, str):
        raise ValueError("not a text value")
    text = value.strip()
    if not text:
        raise ValueError("value is empty")
    if not _NUMBER_PATTERN.fullmatch(text):
        raise ValueError("not a number")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - the pattern already guards this
        raise ValueError("not a number") from exc


def _parse_optional_money(value: object) -> Decimal:
    """Parse Commission or Cashback: empty or an em dash count as 0."""
    if isinstance(value, str) and value.strip() in ("", NO_VALUE):
        return Decimal("0")
    return _parse_money(value)


class Operation(BaseModel):
    """One valid statement row.

    Fields are filled from the CSV cells by column name (the aliases).
    `line` is the line number in the file and `cells` holds every cell of the
    row as text, which duplicate detection compares.
    """

    model_config = ConfigDict(frozen=True)

    line: int
    cells: tuple[str, ...]
    timestamp: datetime = Field(alias=DATE_COLUMN)
    description: str = Field(alias=DESCRIPTION_COLUMN)
    mcc: str | None = Field(alias=MCC_COLUMN)
    amount: Decimal = Field(alias=AMOUNT_COLUMN)
    commission: Decimal = Field(alias=COMMISSION_COLUMN)
    cashback: Decimal = Field(alias=CASHBACK_COLUMN)
    balance: str = Field(alias=BALANCE_COLUMN)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("not a text value")
        text = value.strip()
        if not text:
            raise ValueError("date is missing")
        if not _DATE_PATTERN.fullmatch(text):
            raise ValueError("expected format DD.MM.YYYY HH:MM:SS")
        try:
            return datetime.strptime(text, _DATE_FORMAT)
        except ValueError as exc:
            raise ValueError("not a valid date and time") from exc

    @field_validator("mcc", mode="before")
    @classmethod
    def _parse_mcc(cls, value: object) -> str | None:
        if not isinstance(value, str):
            raise ValueError("not a text value")
        text = value.strip()
        if text in ("", NO_VALUE):
            return None
        if _SHORT_MCC_PATTERN.fullmatch(text):
            # Spreadsheet programs drop leading zeros: "742" means "0742".
            return text.zfill(4)
        return text

    @field_validator("amount", mode="before")
    @classmethod
    def _parse_amount(cls, value: object) -> Decimal:
        return _parse_money(value)

    @field_validator("commission", "cashback", mode="before")
    @classmethod
    def _parse_fee(cls, value: object) -> Decimal:
        return _parse_optional_money(value)

    @property
    def is_income(self) -> bool:
        """A positive amount is income; a negative amount or 0 is an expense."""
        return self.amount > 0

    @property
    def has_balance(self) -> bool:
        """False when Balance is empty or only an em dash."""
        return self.balance.strip() not in ("", NO_VALUE)

    @property
    def counted_amount(self) -> Decimal:
        """Amount that goes into the totals, always >= 0 for expenses."""
        if self.is_income:
            return self.amount
        return max(Decimal("0"), abs(self.amount) + self.commission - self.cashback)


class RowIssue(BaseModel):
    """One problem found in a row.

    `value` is the offending cell text. It is shown in the report but never
    written to logs.
    """

    model_config = ConfigDict(frozen=True)

    column: str | None
    value: str | None
    problem: str


class RejectedRow(BaseModel):
    """A row that failed validation, with its line number and the reasons."""

    model_config = ConfigDict(frozen=True)

    line: int
    issues: tuple[RowIssue, ...]


Mcc = Annotated[str, StringConstraints(pattern=r"^\d{4}$")]


class Rules(BaseModel):
    """Categorization rules loaded from rules.json."""

    model_config = ConfigDict(frozen=True, strict=True)

    categories: dict[Mcc, str]
    income_mccs: frozenset[Mcc]
    own_transfer_patterns: tuple[str, ...]

    @field_validator("own_transfer_patterns")
    @classmethod
    def _patterns_not_blank(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        # An empty pattern is a substring of every Description.
        if any(not pattern.strip() for pattern in patterns):
            raise ValueError("patterns must not be empty or whitespace-only")
        return patterns

    @property
    def category_names(self) -> list[str]:
        """Names accepted by --category: the rules' categories and "uncategorized"."""
        return sorted(set(self.categories.values()), key=str.casefold) + [UNCATEGORIZED]
