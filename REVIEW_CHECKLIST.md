# Code Review Checklist for Agent-Written Code

## Quick pass

Run this on every review. Before each project, replace the examples
(IBAN, credit invoices, `Decimal`) with the sensitive data and business
rules of that project.

- [ ] Does the module import and run, and are all imports real?
- [ ] Is the code free of hardcoded secrets?
- [ ] Are all SQL queries parameterized, with no user input in f-strings?
- [ ] Do logs contain only identifiers, with no raw records, IBANs, amounts, or personal data?
- [ ] Is every rejected or skipped record reported with a reason (no `except Exception: pass`)?
- [ ] Are all spec business rules kept, with no record dropped by an unrequested condition (e.g. credit invoices with `amount < 0`)?
- [ ] Is money `Decimal`, never `float`?
- [ ] Are there no mutable default arguments, and is every connection and file closed?
- [ ] Can each new test fail, and did I see it fail before the fix?
- [ ] Did the agent leave the tests and the spec unchanged (`git diff --stat tests SPEC.md` is empty)?

## 1. Scope: does it do what was asked?

- [ ] Does the code do what the spec asks, nothing more and nothing less?
- [ ] Are all business rules from the spec implemented (e.g. credit invoices with negative amounts are valid)?
- [ ] Is no record filtered out by a condition the spec does not mention (e.g. `if amount > 0`)?
- [ ] Are there no extra features, parameters, or files nobody asked for?
- [ ] Where the agent had to interpret the spec, is that decision recorded in the spec?

## 2. Does it run at all?

- [ ] Does the module import and run without errors on the first try?
- [ ] Are all imports real (the package exists and is installed, the name exists in that package)?
- [ ] Do all called functions, methods, and parameters actually exist in the library version we use?
- [ ] Is every validator or decorator used the way the library documents it (e.g. pydantic `mode="before"` when the input is a raw string)?

## 3. Edge cases

- [ ] Are empty input, `None`, and missing keys handled without a crash or silent skip?
- [ ] Are zero and negative values handled according to the spec?
- [ ] Are duplicates detected by the full business key (e.g. vendor + number), not by one field?
- [ ] Do strings with special characters (quotes, `'`, unicode) work?
- [ ] Are bad formats (dates, numbers) rejected with a clear reason?

## 4. Error handling

- [ ] Are there no bare `except:` or `except Exception: pass` blocks?
- [ ] Is every caught exception specific (e.g. `ValidationError`, not `Exception`)?
- [ ] Is every skipped or rejected record reported (returned with a reason and/or logged)?
- [ ] Are there no stubs that hide failures (`return 0`, `return []`, `pass`, `TODO`)?

## 5. Data and types

- [ ] Is there a clear boundary where raw input becomes a validated model (e.g. pydantic)?
- [ ] Does the boundary return both valid records and rejected records with reasons?
- [ ] Are all functions annotated, and does `mypy --strict` pass?
- [ ] Is money stored and summed as `Decimal`, never `float`?
- [ ] Is every `Decimal` created from a string, never from a `float`?
- [ ] Do sums start from `Decimal("0")`, not `0`?
- [ ] Do internal functions work with typed models, not raw `dict`s?

## 6. Security

- [ ] Is the code free of hardcoded secrets (API keys, passwords, tokens)?
- [ ] Do logs contain only identifiers (e.g. invoice number), not raw records, IBANs, amounts, or personal data?
- [ ] Is raw input returned only to a user who already has access to it (e.g. a rejected record shown to its owner), and never written to logs?
- [ ] Are all SQL queries parameterized (`?` placeholders), with no f-strings or string concatenation of user input?
- [ ] Would an input like `x' OR '1'='1` return nothing instead of every row?

## 7. Tests

- [ ] Do tests exist for every changed behavior?
- [ ] Can each test actually fail? (No tautologies like `assert len(result) >= 0`.)
- [ ] Did I see each new test fail before the fix (red), for the right reason?
- [ ] Do tests check behavior and exact values, not just "no crash"?
- [ ] Are the spec's business rules covered (credit invoice, same number from two vendors)?
- [ ] Do tests run a function twice to catch state leaking between calls?
- [ ] Is there a test that sensitive data is absent from logs (e.g. via `caplog`)?
- [ ] Do tests use temporary resources (`tmp_path`, `monkeypatch`) instead of real databases or files?
- [ ] Does every test name point to the spec criterion it checks?

## 8. Resources and state

- [ ] Are there no mutable default arguments (`def f(seen=set())`, `def f(items=[])`)?
- [ ] Is every database connection closed, even on error (`with closing(...)`)?
- [ ] Is every file opened with `with`?
- [ ] Does calling a function twice give the same result (no hidden shared state)?

## 9. Readability

- [ ] Are names clear and do they say what the thing is?
- [ ] Is the code free of duplication and dead code?
- [ ] Are debug `print` calls removed from library functions?
- [ ] Are review comments and leftover notes removed from the final code?
- [ ] Are magic values (date formats, paths) named constants?
