"""Shared fixtures: statement row factory, CSV writer and a minimal rules file."""

import csv
import json

import pytest

HEADER = [
    "Date and time",
    "Description",
    "MCC",
    "Card currency amount, (UAH)",
    "Operation amount",
    "Operation currency",
    "Exchange rate",
    "Commission, (UAH)",
    "Cashback amount, (UAH)",
    "Balance",
]

RULES = {
    "categories": {
        "5411": "Groceries",
        "5812": "Restaurants",
        "4829": "Transfers",
    },
    "income_mccs": ["4829"],
    "own_transfer_patterns": [
        "поповнення особистого рахунку",
        "переказ на особистий рахунок",
    ],
}


def make_row(
    date="05.10.2026 12:00:00",
    description="Сільпо",
    mcc="5411",
    amount="-100.00",
    operation_amount="-100.00",
    operation_currency="UAH",
    exchange_rate="",
    commission="",
    cashback="",
    balance="1000.00",
):
    """Return one statement row as {column name: cell text} with valid defaults.

    Two rows that are equal in every column, Balance included, are duplicates.
    Tests that need several rows always make them differ in some column.
    """
    return {
        "Date and time": date,
        "Description": description,
        "MCC": mcc,
        "Card currency amount, (UAH)": amount,
        "Operation amount": operation_amount,
        "Operation currency": operation_currency,
        "Exchange rate": exchange_rate,
        "Commission, (UAH)": commission,
        "Cashback amount, (UAH)": cashback,
        "Balance": balance,
    }


@pytest.fixture
def write_statement(tmp_path):
    """Return a function that writes a header and rows to a CSV file in tmp_path.

    A row is a dict from make_row, or None for an empty line.
    """

    def _write(rows, name="statement.csv", header=HEADER, bom=False):
        path = tmp_path / name
        encoding = "utf-8-sig" if bom else "utf-8"
        with open(path, "w", encoding=encoding, newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in rows:
                if row is None:
                    writer.writerow([])
                else:
                    writer.writerow([row[column] for column in header])
        return path

    return _write


@pytest.fixture
def rules_path(tmp_path):
    """Write the minimal rules file from SPEC.md to tmp_path and return its path."""
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(RULES), encoding="utf-8")
    return path
