# Bank Statement Analyzer

A command-line tool for people who keep a personal budget: export a monthly Monobank statement, run one command, and see where the money went, broken down by category, without logging every purchase by hand.

## Quick start

Tested on Python 3.14.

```bash
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell
# .venv\Scripts\activate.bat       # Windows cmd
pip install -r requirements.txt

python -m analyzer report path/to/statement.csv
```

If PowerShell refuses to run `Activate.ps1`, allow local scripts once with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Options:

```
python -m analyzer report FILE [--rules PATH] [--from YYYY-MM-DD] [--to YYYY-MM-DD]
                     [--category NAME] [--only-income | --only-expenses]
```

Categories come from [`rules.json`](rules.json), which maps MCC codes to category names. Edit it to add your own categories and the descriptions of transfers between your own accounts.

## Example

[`examples/sample_statement.csv`](examples/sample_statement.csv) is a synthetic statement with 12 operations. It includes four expense categories, a salary, a foreign-currency payment, a row without an MCC, a refund, a transfer between own accounts, a row exported twice and a row with a broken amount.

```
$ python -m analyzer report examples/sample_statement.csv
Period: 01.10.2026 - 20.10.2026
Total expenses: 3333.19 UAH
Total income: 25000.00 UAH
Net: 21666.81 UAH

Expenses by category
  Category                    Amount, UAH   Share Operations
  Groceries                       2109.39   63.3%          2
  Subscriptions                    415.80   12.5%          1
  Restaurants                      380.00   11.4%          1
  uncategorized                    255.00    7.7%          1
  Transport                        173.00    5.2%          2

Income by category
  Category                    Amount, UAH   Share Operations
  Transfers                      25000.00  100.0%          1

Uncategorized operations
  12.10.2026 10:10:10  Оплата за QR-кодом  -255.00  —  no MCC

Excluded operations
  08.10.2026 11:22:09  Поповнення особистого рахунку  -5000.00  own transfer
  10.10.2026 16:45:33  Повернення: Сільпо  149.90  refund

Warnings
  Duplicate: lines 5, 6 are the same operation exported more than once, counted once

Rejected rows
  Line 12: column "Card currency amount, (UAH)" value "n/a": not a number
```

Groceries is 2109.39 rather than 1245.60 + 876.25 because the 12.46 cashback is subtracted. The uncategorized payment is 255.00 because its 5.00 commission is added. No row disappears silently: every row is counted, excluded with a reason, flagged as a duplicate, or rejected with its line number.

## How it works

Each valid row goes through these steps in order, and the first match decides:

- The description matches an own-transfer pattern: the row is excluded, because moving money between your own accounts is neither spending nor income.
- The amount is positive and its MCC is not an income MCC: the row is excluded as a refund. Refunds are not netted against purchases, because a refund can arrive in a different month and make a category negative.
- Otherwise the row is counted as an expense or income in the category that `rules.json` gives for its MCC.
- A row with no MCC, or with an MCC that the rules do not cover, is counted in `uncategorized` and listed with the reason.

The full behavior, including edge cases and the acceptance criteria, is in [SPEC.md](SPEC.md).

## Design decisions

- **Money is `Decimal`, parsed straight from the CSV text.** Floats cannot represent most amounts exactly, so a month of sums would drift by kopecks. Parsing from the string, not from a float, keeps every amount exact from the file to the report.
- **Input is validated once, at the boundary, with strict patterns.** Pydantic models with regular expressions accept only `DD.MM.YYYY HH:MM:SS` dates and plain numbers. A value such as `1e3` or `12,50` is rejected with its column and line instead of being misread, and the rest of the code works only with validated data.
- **Confirmed and possible duplicates are different.** Two identical purchases at the same second are possible, but they leave different balances. Rows that match in every column, including Balance, are one operation exported twice and are counted once. When Balance is empty, duplication cannot be proven, so every row is counted and only a warning is shown.
- **Row numbers are physical line numbers in the file.** They come from the CSV reader's `line_num`, not from counting records. A description with a line break inside quotes, or a skipped empty line, does not shift the numbers, so a rejected row points to the line you see in your editor.
- **`main()` returns the exit code instead of exiting.** Errors map to exit codes 0, 1 and 2. Because `main(argv)` never calls `sys.exit`, tests drive the program in-process exactly as the command line does, and no test needs a subprocess.

## Testing

```bash
pip install -r requirements-dev.txt    # adds pytest and mypy
python -m pytest
python -m mypy --strict analyzer
```

64 tests cover all 35 acceptance criteria in [SPEC.md](SPEC.md). Each test name starts with the number of the criterion it checks (`test_ac29_empty_lines_are_skipped_but_keep_line_numbers`), so every rule in the spec can be traced to a test and back. The tests run the real command through `main(argv)` and check the exit code and the key parts of the output. The code passes `mypy --strict`.

## Results

- **Categorization rate:** on a real one-month statement, 84 of 86 operations (97.7%) got a category automatically. The target in the brief was at least 90%.
- **Speed:** the full report for that statement takes about 0.6–0.7 s on Windows 11, including Python start-up. The target was under a minute.
- **Privacy:** the tool runs locally and makes no network calls. Statements never leave your machine, and `.gitignore` keeps every CSV except the synthetic examples out of the repository.

## Limitations

- Own-transfer patterns have been tested only on synthetic data. If your transfers between your own accounts are described differently, add that wording to `own_transfer_patterns` in `rules.json`.
- Only the Monobank CSV statement is supported.
- Categories depend on MCC codes. A shop with a misleading MCC lands in the wrong category, and there is no override by description.

## How it was built

I built this spec-first, with an AI coding agent writing the implementation. I started with a short [brief](BRIEF.md) (in Ukrainian) that sets the problem, the audience and the success targets. I turned it into [SPEC.md](SPEC.md), with numbered Given/When/Then acceptance criteria, and wrote the tests from the spec before any code existed. A coding agent then wrote the implementation and was not allowed to change the tests or the spec; the git history confirms it did not.I reviewed the code against [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md) and each fix went in test-first: a new criterion in the spec, a failing test, then the code. I answered every open question the agent raised and wrote the decisions back into the spec.

## Possible improvements

- List the operations of each category, not only the totals.
- Support statements from other banks behind the same validated models.
- Export the report as CSV or JSON for spreadsheets and other tools.

## License

[MIT](LICENSE)
