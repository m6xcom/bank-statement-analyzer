"""Acceptance tests for SPEC.md.

Each test name starts with acNN, the number of the acceptance criterion it
checks. Tests drive the program only through analyzer.cli.main(argv) and look
at the exit code and key fragments of the output, never at the full report.

Amounts are checked with a plain `in`, so test amounts are chosen so that
one never sits inside another (for example, no "105.00" next to "1105.00").
"""

import json

import pytest

from analyzer.cli import main
from conftest import HEADER, RULES, make_row


# --- output helpers -------------------------------------------------------


def line_with(text, fragment):
    """Return the first line of the output that contains `fragment`."""
    lines = [line for line in text.splitlines() if fragment in line]
    assert lines, f"no line contains {fragment!r} in output:\n{text}"
    return lines[0]


def words(line):
    """Split a line into words, treating : , ; ( ) | % as spaces."""
    for char in ":,;()|%":
        line = line.replace(char, " ")
    return line.split()


def has_count(line, n):
    """True if the number `n` is a separate word on the line.

    A plain `in` is not enough here: "1" is inside "105.00".
    """
    return str(n) in words(line)


def error_output(capsys):
    """Errors may go to stdout or stderr; the spec does not say which."""
    captured = capsys.readouterr()
    return captured.out + captured.err


# --- AC1 ------------------------------------------------------------------


def test_ac01_expenses_grouped_by_category_with_sum_share_count_and_order(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="4829", amount="-50.00", description="Переказ Іванові"),
        make_row(mcc="5812", amount="-150.00", description="Пузата хата"),
        make_row(mcc="5411", amount="-300.00"),
        make_row(mcc="5411", amount="-200.00"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "700.00" in out, "total expenses"

    groceries = line_with(out, "Groceries")
    assert "500.00" in groceries
    assert "71.4" in groceries
    assert has_count(groceries, 2)

    restaurants = line_with(out, "Restaurants")
    assert "150.00" in restaurants
    assert "21.4" in restaurants
    assert has_count(restaurants, 1)

    transfers = line_with(out, "Transfers")
    assert "50.00" in transfers
    assert "7.1" in transfers
    assert has_count(transfers, 1)

    assert out.index("Groceries") < out.index("Restaurants") < out.index("Transfers")


# --- AC2 ------------------------------------------------------------------


def test_ac02_income_and_expenses_in_separate_sections_and_net(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="4829", amount="800.00", description="From: Іван Петренко"),
        make_row(mcc="5411", amount="-300.00"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "300.00" in out, "total expenses"
    assert "800.00" in out, "total income"
    assert "500.00" in out, "net = income - expenses"

    groceries = line_with(out, "Groceries")
    transfers = line_with(out, "Transfers")
    assert "300.00" in groceries and "800.00" not in groceries
    assert "800.00" in transfers and "300.00" not in transfers
    assert out.index("Groceries") < out.index("Transfers"), "expenses before income"


# --- AC3 ------------------------------------------------------------------


def test_ac03_expense_includes_commission_minus_cashback(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(amount="-100.00", commission="10.00", cashback="5.00", mcc="5411"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 0
    assert "105.00" in line_with(capsys.readouterr().out, "Groceries")


# --- AC4 ------------------------------------------------------------------


def test_ac04_foreign_currency_amount_taken_from_card_currency_column(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(
            mcc="5411",
            amount="-410.00",
            operation_amount="-10.00",
            operation_currency="USD",
            exchange_rate="41.0",
        ),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 0
    groceries = line_with(capsys.readouterr().out, "Groceries")
    assert "410.00" in groceries
    assert has_count(groceries, 1)


# --- AC5 ------------------------------------------------------------------


def test_ac05_date_filter_includes_both_boundary_days(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(date="30.09.2026 23:59:59", amount="-100.00"),
        make_row(date="01.10.2026 00:00:00", amount="-200.00"),
        make_row(date="15.10.2026 23:59:59", amount="-40.00"),
        make_row(date="16.10.2026 00:00:00", amount="-800.00"),
    ])

    code = main([
        "report", str(path), "--rules", str(rules_path),
        "--from", "2026-10-01", "--to", "2026-10-15",
    ])

    out = capsys.readouterr().out
    assert code == 0
    groceries = line_with(out, "Groceries")
    assert "240.00" in groceries
    assert has_count(groceries, 2)
    assert "100.00" not in out, "30.09 is before the period"
    assert "800.00" not in out, "16.10 is after the period"


# --- AC6 ------------------------------------------------------------------


def test_ac06_rows_without_mcc_or_unknown_mcc_are_uncategorized_and_counted(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="5411", amount="-100.00"),
        make_row(mcc="", amount="-70.00", description="Без MCC"),
        make_row(mcc="7995", amount="-40.00", description="Лотерея"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "210.00" in out, "total expenses include uncategorized rows"
    assert "110.00" in out, "uncategorized category sum"
    assert "70.00" in line_with(out, "no MCC")
    assert "40.00" in line_with(out, "MCC 7995 not in rules")


# --- AC7 ------------------------------------------------------------------


def test_ac07_only_income_and_only_expenses_together_is_argument_error(
    write_statement, rules_path
):
    path = write_statement([make_row()])

    code = main([
        "report", str(path), "--rules", str(rules_path),
        "--only-income", "--only-expenses",
    ])

    assert code == 2


# --- AC8 ------------------------------------------------------------------


def test_ac08_non_numeric_amount_rejects_only_that_row(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(amount="-100.00"),
        make_row(amount="n/a"),
        make_row(amount="-20.00"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    rejected = line_with(out, "n/a")
    assert "Card currency amount, (UAH)" in rejected
    assert has_count(rejected, 3), "line number: header is line 1, n/a row is line 3"
    groceries = line_with(out, "Groceries")
    assert "120.00" in groceries
    assert has_count(groceries, 2)


# --- AC9 ------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_date", ["32.13.2026 25:00:00", "2026-10-05 12:00:00", ""]
)
def test_ac09_row_with_missing_or_unparsable_date_is_rejected(
    write_statement, rules_path, capsys, bad_date
):
    path = write_statement([
        make_row(date="05.10.2026 12:00:00", amount="-100.00"),
        make_row(date=bad_date, amount="-55.00"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    rejected = line_with(out, "Date and time")
    assert has_count(rejected, 3), "line number: header is line 1, bad row is line 3"
    assert "100.00" in line_with(out, "Groceries")
    assert "155.00" not in out, "rejected row is not counted"


def test_ac09_row_without_date_is_rejected_with_date_filters(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(date="05.10.2026 12:00:00", amount="-100.00"),
        make_row(date="", amount="-55.00"),
    ])

    code = main([
        "report", str(path), "--rules", str(rules_path),
        "--from", "2026-10-01", "--to", "2026-10-31",
    ])

    out = capsys.readouterr().out
    assert code == 0
    assert has_count(line_with(out, "Date and time"), 3)
    assert "100.00" in line_with(out, "Groceries")


# --- AC10 -----------------------------------------------------------------


def test_ac10_empty_file_reports_no_operations(rules_path, capsys, tmp_path):
    path = tmp_path / "statement.csv"
    path.write_text("")

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 0
    assert "Statement contains no operations" in capsys.readouterr().out


def test_ac10_header_only_reports_no_operations(write_statement, rules_path, capsys):
    path = write_statement([])

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 0
    assert "Statement contains no operations" in capsys.readouterr().out


# --- AC11 -----------------------------------------------------------------


def test_ac11_missing_statement_file_is_error(rules_path, capsys, tmp_path):
    path = tmp_path / "nope.csv"

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 1
    assert "nope.csv" in error_output(capsys)


@pytest.mark.parametrize("name", ["statement.txt", "statement.xlsx", "statement"])
def test_ac11_statement_without_csv_extension_is_error(
    write_statement, rules_path, capsys, name
):
    path = write_statement([make_row()], name=name)

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 1
    assert "csv" in error_output(capsys).lower()


def test_ac11_csv_extension_is_case_insensitive(
    write_statement, rules_path, capsys
):
    path = write_statement([make_row(amount="-100.00")], name="STATEMENT.CSV")

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 0
    assert "100.00" in line_with(capsys.readouterr().out, "Groceries")


# --- AC12 -----------------------------------------------------------------


def test_ac12_missing_rules_file_error_shows_full_path(
    write_statement, capsys, tmp_path
):
    statement = write_statement([make_row()])
    rules = tmp_path / "custom-rules.json"

    code = main(["report", str(statement), "--rules", str(rules)])

    assert code == 1
    assert str(rules) in error_output(capsys)


def test_ac12_invalid_json_rules_file_error_shows_full_path(
    write_statement, capsys, tmp_path
):
    statement = write_statement([make_row()])
    rules = tmp_path / "custom-rules.json"
    rules.write_text("{not json", encoding="utf-8")

    code = main(["report", str(statement), "--rules", str(rules)])

    assert code == 1
    assert str(rules) in error_output(capsys)


@pytest.mark.parametrize("key", ["categories", "income_mccs", "own_transfer_patterns"])
def test_ac12_rules_file_without_required_key_error_shows_full_path(
    write_statement, capsys, tmp_path, key
):
    statement = write_statement([make_row()])
    incomplete = dict(RULES)
    del incomplete[key]
    rules = tmp_path / "custom-rules.json"
    rules.write_text(json.dumps(incomplete), encoding="utf-8")

    code = main(["report", str(statement), "--rules", str(rules)])

    assert code == 1
    assert str(rules) in error_output(capsys)


def test_ac12_without_rules_flag_reads_rules_json_from_project_root(
    write_statement, capsys, monkeypatch, tmp_path
):
    statement = write_statement([make_row(mcc="5411", amount="-100.00")])
    # Run from a directory that has no rules.json: the program must still
    # find the default file in the project root, not in the current directory.
    monkeypatch.chdir(tmp_path)

    code = main(["report", str(statement)])

    assert code == 0, error_output(capsys)


# --- AC13 -----------------------------------------------------------------


def test_ac13_positive_amount_with_non_income_mcc_is_excluded_as_refund(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="5411", amount="-100.00"),
        make_row(mcc="5411", amount="250.00", description="Повернення Сільпо"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "refund" in line_with(out, "250.00")
    assert "150.00" not in out, "refund is not subtracted from expenses"
    assert "350.00" not in out, "refund is not added anywhere"


# --- AC14 -----------------------------------------------------------------


def test_ac14_own_transfers_are_excluded_case_insensitively(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="5411", amount="-100.00"),
        make_row(mcc="4829", amount="300.00", description="Поповнення особистого рахунку"),
        make_row(mcc="4829", amount="-200.00", description="Переказ на особистий рахунок"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "own transfer" in line_with(out, "300.00")
    assert "own transfer" in line_with(out, "200.00")
    assert "Transfers" not in out, "no Transfers category is counted"


# --- AC15 -----------------------------------------------------------------


def test_ac15_rows_identical_including_balance_counted_once_with_warning(
    write_statement, rules_path, capsys
):
    row = make_row(mcc="5411", amount="-100.00", balance="5000.00")
    path = write_statement([row, row])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    groceries = line_with(out, "Groceries")
    assert "100.00" in groceries
    assert has_count(groceries, 1)
    assert "200.00" not in out
    assert "possible duplicate" not in out.lower()
    warning = line_with(out.lower(), "duplicate")
    assert has_count(warning, 2) and has_count(warning, 3), "warning names lines 2 and 3"


# --- AC16 -----------------------------------------------------------------


def test_ac16_rows_differing_only_in_balance_are_both_counted(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="5411", amount="-100.00", balance="5000.00"),
        make_row(mcc="5411", amount="-100.00", balance="4900.00"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    groceries = line_with(out, "Groceries")
    assert "200.00" in groceries
    assert has_count(groceries, 2)
    assert "duplicate" not in out.lower()


# --- AC17 -----------------------------------------------------------------


def test_ac17_utf8_bom_gives_same_report_as_without_bom(
    write_statement, rules_path, capsys
):
    rows = [
        make_row(mcc="5411", amount="-100.00"),
        make_row(mcc="5812", amount="-60.00", description="Кафе"),
        make_row(mcc="4829", amount="500.00", description="From: Іван Петренко"),
    ]

    path = write_statement(rows, bom=False)
    code_plain = main(["report", str(path), "--rules", str(rules_path)])
    out_plain = capsys.readouterr().out

    write_statement(rows, bom=True)  # same file name, now with BOM
    code_bom = main(["report", str(path), "--rules", str(rules_path)])
    out_bom = capsys.readouterr().out

    assert code_plain == 0
    assert code_bom == 0
    assert "100.00" in line_with(out_bom, "Groceries")
    assert out_bom == out_plain


# --- AC18 -----------------------------------------------------------------


def test_ac18_cashback_larger_than_expense_counts_as_zero_but_one_operation(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="5411", amount="-10.00", commission="", cashback="15.00"),
        make_row(mcc="5812", amount="-50.00", description="Кафе"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    groceries = line_with(out, "Groceries")
    assert "0.00" in groceries
    assert "10.00" not in groceries, "cashback is applied"
    assert has_count(groceries, 1)
    assert "50.00" in out, "total expenses"
    assert "45.00" not in out, "negative expense must not reduce the total"


# --- AC19 -----------------------------------------------------------------


@pytest.mark.parametrize(
    "commission, cashback, expected",
    [
        ("—", "—", "100.00"),
        ("—", "5.00", "95.00"),
        ("10.00", "—", "110.00"),
    ],
)
def test_ac19_em_dash_in_commission_or_cashback_counts_as_zero(
    write_statement, rules_path, capsys, commission, cashback, expected
):
    path = write_statement([
        make_row(
            mcc="5411",
            amount="-100.00",
            exchange_rate="—",
            commission=commission,
            cashback=cashback,
        ),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 0
    groceries = line_with(capsys.readouterr().out, "Groceries")
    assert expected in groceries
    assert has_count(groceries, 1), "row is counted, not rejected"


# --- AC20 -----------------------------------------------------------------


@pytest.mark.parametrize("column", ["MCC", "Card currency amount, (UAH)", "Balance"])
def test_ac20_missing_required_column_is_error_naming_the_column(
    write_statement, rules_path, capsys, column
):
    header = [name for name in HEADER if name != column]
    path = write_statement([make_row()], header=header)

    code = main(["report", str(path), "--rules", str(rules_path)])

    assert code == 1
    assert column in error_output(capsys)


# --- AC21 -----------------------------------------------------------------


def test_ac21_from_later_than_to_is_argument_error(write_statement, rules_path):
    path = write_statement([make_row()])

    code = main([
        "report", str(path), "--rules", str(rules_path),
        "--from", "2026-10-15", "--to", "2026-10-01",
    ])

    assert code == 2


# --- AC22 -----------------------------------------------------------------


THREE_CATEGORIES = [
    make_row(mcc="5411", amount="-100.00"),
    make_row(mcc="5812", amount="-60.00", description="Кафе"),
    make_row(mcc="", amount="-30.00", description="Без MCC"),
]


def test_ac22_category_filter_shows_only_that_category(
    write_statement, rules_path, capsys
):
    path = write_statement(THREE_CATEGORIES)

    code = main([
        "report", str(path), "--rules", str(rules_path), "--category", "Groceries",
    ])

    out = capsys.readouterr().out
    assert code == 0
    assert "100.00" in line_with(out, "Groceries")
    assert "Restaurants" not in out
    assert "no MCC" not in out
    assert "60.00" not in out
    assert "30.00" not in out
    assert "190.00" not in out


def test_ac22_category_filter_accepts_uncategorized(
    write_statement, rules_path, capsys
):
    path = write_statement(THREE_CATEGORIES)

    code = main([
        "report", str(path), "--rules", str(rules_path), "--category", "uncategorized",
    ])

    out = capsys.readouterr().out
    assert code == 0
    assert "30.00" in line_with(out, "no MCC")
    assert "Groceries" not in out
    assert "Restaurants" not in out
    assert "60.00" not in out
    assert "190.00" not in out


# --- AC23 -----------------------------------------------------------------


INCOME_AND_EXPENSE = [
    make_row(mcc="4829", amount="800.00", description="From: Іван Петренко"),
    make_row(mcc="5411", amount="-300.00"),
]


def test_ac23_only_expenses_hides_income(write_statement, rules_path, capsys):
    path = write_statement(INCOME_AND_EXPENSE)

    code = main(["report", str(path), "--rules", str(rules_path), "--only-expenses"])

    out = capsys.readouterr().out
    assert code == 0
    assert "300.00" in line_with(out, "Groceries")
    assert "Transfers" not in out
    assert "800.00" not in out
    assert "500.00" not in out, "net uses only expenses"


def test_ac23_only_income_hides_expenses(write_statement, rules_path, capsys):
    path = write_statement(INCOME_AND_EXPENSE)

    code = main(["report", str(path), "--rules", str(rules_path), "--only-income"])

    out = capsys.readouterr().out
    assert code == 0
    assert "800.00" in line_with(out, "Transfers")
    assert "Groceries" not in out
    assert "300.00" not in out
    assert "500.00" not in out, "net uses only income"


# --- AC24 -----------------------------------------------------------------


def test_ac24_identical_rows_with_empty_balance_are_possible_duplicates(
    write_statement, rules_path, capsys
):
    row = make_row(mcc="5411", amount="-100.00", balance="")
    path = write_statement([row, row])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    groceries = line_with(out, "Groceries")
    assert "200.00" in groceries
    assert has_count(groceries, 2)
    warning = line_with(out.lower(), "possible duplicate")
    assert has_count(warning, 2) and has_count(warning, 3), "warning names lines 2 and 3"


# --- AC25 -----------------------------------------------------------------


def test_ac25_income_without_mcc_is_uncategorized_income_not_refund(
    write_statement, rules_path, capsys
):
    path = write_statement([
        make_row(mcc="5411", amount="-100.00"),
        make_row(mcc="", amount="350.00", description="Готівка"),
    ])

    code = main(["report", str(path), "--rules", str(rules_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "refund" not in out.lower()
    assert "350.00" in line_with(out, "no MCC")
    assert "250.00" in out, "net = 350.00 income - 100.00 expenses"
