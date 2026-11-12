# Bank Statement Analyzer — Specification

## Goal
Help people who keep a personal budget see where their money went without logging every purchase by hand. The user exports a monthly Monobank statement, runs one command and gets expenses and income broken down by category.

## Input

### Statement
- Monobank card statement, CSV, UTF-8 with or without BOM, comma-delimited, first row is the header.
- The file is recognized as CSV by its extension: `.csv`, case-insensitive. Any other problem with the content is reported as a missing required column or as rejected rows.
- Required columns: "Date and time", Description, MCC, "Card currency amount, (UAH)", "Operation amount", "Operation currency", "Exchange rate", "Commission, (UAH)", "Cashback amount, (UAH)", Balance.
- Date and time format: `DD.MM.YYYY HH:MM:SS`.
- The amount is always taken from "Card currency amount, (UAH)". The bank has already converted foreign-currency operations to UAH, so "Operation amount", "Operation currency" and "Exchange rate" are not used.
- A negative amount is an expense, a positive amount is income.
- "Card currency amount, (UAH)" does not include the commission. Final amounts:
  - Expense = max(0, |Card currency amount| + Commission − Cashback). An expense never goes below 0; such a row is still counted in the number of operations.
  - Income = Card currency amount
  - An empty Commission or Cashback cell counts as 0.

### Rules file
- Default location: `rules.json` in the same directory as the program. It can be overridden with `--rules PATH`.
- The project ships with a default `rules.json` that maps common MCCs to categories. The user edits it to add categories and their own-transfer patterns.
- JSON object with three required keys:
  - `categories` — MCC (4-digit string) → category name. Used for both expenses and income.
  - `income_mccs` — MCCs for which a positive amount is real income (for example, incoming transfers). A positive amount with any other MCC is treated as a refund.
  - `own_transfer_patterns` — substrings of Description that mark a transfer between the user's own accounts. Matching is case-insensitive.
- Example:
  ```json
  {
    "categories": {
      "5411": "Groceries",
      "5812": "Restaurants",
      "4829": "Transfers"
    },
    "income_mccs": ["4829"],
    "own_transfer_patterns": [
      "поповнення особистого рахунку",
      "переказ на особистий рахунок"
    ]
  }
  ```

## Command line

```
python -m analyzer report FILE [--rules PATH] [--from YYYY-MM-DD] [--to YYYY-MM-DD]
                     [--category NAME] [--only-income | --only-expenses]
```

- `FILE` — path to the statement (required).
- `--rules PATH` — path to the rules file. Optional; used mainly for tests and for trying alternative rules. Default: `rules.json` next to the program.
- `--from YYYY-MM-DD` — include operations on or after this date (inclusive). Default: start of the statement.
- `--to YYYY-MM-DD` — include operations on or before this date (inclusive). Default: end of the statement.
- A single day is `--from 2026-10-05 --to 2026-10-05`.
- `--from` later than `--to` is an argument error.
- `--category NAME` — show only this category (`uncategorized` is a valid name). Default: all categories.
- `--only-income` and `--only-expenses` are mutually exclusive.

### Exit codes
- `0` — report produced (including an empty statement, an empty result after filters, or rejected rows).
- `1` — file or data error: statement not found or unreadable, file extension is not `.csv`, a required column is missing; rules file missing, not valid JSON, or missing a required key.
- `2` — invalid arguments (returned by argparse).

## Categorization rules
Each valid row goes through these steps in order; the first step that matches decides:
1. Description contains one of `own_transfer_patterns` → excluded as "own transfer", not counted.
2. Amount is positive and MCC is present but not in `income_mccs` → excluded as "refund", not counted. Refunds are ignored because a refund can arrive in a different statement than the purchase, and subtracting it could make a category negative.
3. Otherwise the row is counted as an expense or income, and its category is looked up by MCC in `categories`.
4. A row with no MCC, or with an MCC not in `categories`, goes to `uncategorized` and is counted in all totals.

## Output
The report is printed in this order:

1. Summary: period (first and last date of the included operations), total expenses, total income, net (income − expenses).
2. Expenses by category, sorted by amount, largest first: category, sum in UAH, share of total expenses in %, number of operations. `uncategorized` takes its place by amount.
3. Income by category, same format.
4. Uncategorized operations: date, description, amount, MCC (or "—"), reason ("no MCC" or "MCC 1234 not in rules").
5. Excluded operations: date, description, amount, reason ("refund" or "own transfer").
6. Warnings: confirmed duplicates (counted once) and possible duplicates (counted every time), with row numbers.
7. Rejected rows: row number and a reason that names the column and its value.

Amounts are shown with 2 decimal places, shares with 1. Sections that are empty or hidden by filters are not printed.

## Edge cases
- Empty file or header only: the report says "Statement contains no operations", exit 0.
- No operations left after filters: the report says so, exit 0.
- A required column is missing: error that names the column, exit 1.
- Broken row (amount is not a number, date is missing or doesn't parse, wrong number of fields): the row is rejected with a reason, all other rows are counted. A row without a date is always rejected, regardless of filters.
- Duplicates: two rows are duplicates only if all columns match, including Balance. Balance is the account balance after the operation, so two real identical purchases at the same second still have different balances. An identical Balance means the same operation was exported twice. A confirmed duplicate is counted once and listed in Warnings.
- If rows match in all columns but Balance is empty, duplication cannot be confirmed: every row is counted and listed in Warnings as a possible duplicate.

## Acceptance criteria
1. Given a valid statement with expenses in several categories covered by the rules, when I run the report, then each category shows the correct sum, share and number of operations, categories are sorted by sum descending, and the total equals the sum of all expense rows.
2. Given a statement with both income and expenses, when I run the report, then they appear in separate sections and net equals income minus expenses.
3. Given an expense of −100.00 with commission 10.00 and cashback 5.00, when I run the report, then it is counted as 105.00.
4. Given an operation in USD, when I run the report, then its amount is taken from "Card currency amount, (UAH)" and the row is not rejected.
5. Given `--from 2026-10-01 --to 2026-10-15`, when I run the report, then only operations from those dates are counted, including operations on both boundary days.
6. Given one row with no MCC and one row with an MCC that is not in `categories`, when I run the report, then both are counted in the totals and appear in the uncategorized list with their reasons.
7. Given `--only-income` and `--only-expenses` together, when I run the report, then I see an argument error and the exit code is 2.
8. Given a statement where one row has the amount "n/a", when I run the report, then that row appears in the rejected list with a reason that names the amount column, and all other rows are counted.
9. Given a statement where one row has no date or a date that doesn't parse, when I run the report with or without date filters, then that row appears in the rejected list.
10. Given an empty statement, when I run the report, then I see "Statement contains no operations" and the exit code is 0.
11. Given a statement path that doesn't exist or a file whose extension is not `.csv`, when I run the report, then I see an error that names the problem and the exit code is 1.
12. Given a rules file (default or passed with `--rules`) that is missing, is not valid JSON, or lacks a required key, when I run the report, then I see an error that shows the full path of the rules file and the exit code is 1.
13. Given an income row of +250.00 with MCC 5411, which is not in `income_mccs`, when I run the report, then it appears in the excluded list as "refund" and is not counted in any total.
14. Given one row with "Поповнення особистого рахунку" and one row with "Переказ на особистий рахунок" in Description, when I run the report, then both appear in the excluded list as "own transfer" and neither is counted in any total.
15. Given two rows identical in all columns including Balance, when I run the report, then the operation is counted once and listed in Warnings as a duplicate.
16. Given two rows identical in all columns except Balance, when I run the report, then both are counted and no duplicate warning is shown.
17. Given a valid statement saved in UTF-8 with BOM, when I run the report, then all required columns are found and the report is the same as for the file without BOM.
18. Given an expense of −10.00 with cashback 15.00 and no commission, when I run the report, then it is counted as 0.00 and still adds 1 to the category's number of operations.

## Non-goals
- **No website.** We are not building a web version of the product.
- **Single statement format.** Only the Monobank CSV statement is supported.
- **Rule-based categorization only.** Operations are categorized by MCC rules, with no AI.
- **No forecasting.** The app does not predict future spending.
- **No refund matching.** Refunds are ignored and never netted against purchases.
- **No features for sole proprietors or small-business accounting.** The app is for personal finances only.