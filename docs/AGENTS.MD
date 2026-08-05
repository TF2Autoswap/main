# Project Rules - Verification Standards

## Claims must be backed by execution, not assertion
- Never report a test count, coverage %, or "passing" status without
  actually running the test/coverage command in this session and
  showing the real output.
- If a number is estimated rather than measured, label it clearly as
  an estimate — never round up or imply more confidence than the data
  supports.
- "Fixed" means: changed AND re-tested AND confirmed working. Not just changed.
- When summarizing or breaking down a number from a report, the parts must sum to the whole — check this before presenting it, the same way overall totals get checked.
## Security-critical code gets adversarial tests first
- Any code that parses untrusted input (files from tf/custom/, user-provided
  paths, etc.) needs attack-focused tests (oversized input, malformed data,
  path traversal, encoding edge cases) BEFORE happy-path tests.
- Do not report high coverage on a module without specifying whether the
  tests are adversarial or just valid-input checks.

- Default to requiring explicit human approval before file changes. Only skip approval if the user has stated a specific task doesn't need oversight.

- no absolute claims (100%, every single line, all) without checking them against the actual per-file coverage report first.
## Documentation must reflect actual code, not aspirational standards
- If DEVELOPMENT.md states a standard (e.g. custom exceptions, function
  length limits) that the code doesn't currently follow, flag this
  explicitly rather than silently leaving the gap.

## File metadata
- Author field: Melancholy Sky. Co-author credit for AI assistance is fine
  and appreciated, but never replace or omit the primary author.
- License field must match the project's actual LICENSE file (GPL v3) —
  check this explicitly on every new file.
  
- Don't use Emoji within documentation

- Don't try to up-sell my own project to me, e.g. over usage of emoji & hype language keep it professional & realistic.
