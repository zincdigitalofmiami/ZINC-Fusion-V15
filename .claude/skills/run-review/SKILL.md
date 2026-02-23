---
name: run-review
description: Use when the user says "review my code", "check my changes", "run a review", "anything I should fix before merging", or wants a pre-commit or pre-PR quality check on local changes. Runs both CodeScene (structural code health) and cubic (AI semantic review) then surfaces all issues grouped by severity.
---

# Run Local Code Review

This skill runs a **two-layer** local code review:
1. **CodeScene** — deterministic structural analysis (complexity, method size, nesting, code smells)
2. **cubic** — AI semantic review (logic bugs, security issues, missing edge cases)

Both tools are complementary. CodeScene catches what's objectively measurable; cubic catches what requires understanding intent.

## When to Activate

- User says "review my code", "check my changes", "run a review", or "anything I should fix"
- User is about to commit or open a PR and wants a quality check
- User asks to "scan for issues", "check for problems", or "review before merging"

## Layer 1: CodeScene (Structural Health)

The CodeScene CLI is bundled with the VS Code extension. Use the binary directly.

### Setup

```
CS="$HOME/.vscode/extensions/codescene.codescene-vscode-0.26.1-darwin-arm64/cs-darwin-arm64"
```

If the binary doesn't exist, look for any matching extension:
```
ls ~/.vscode/extensions/codescene.codescene-vscode-*/cs-darwin-arm64
```

If nothing found, tell the user to install the CodeScene VS Code extension.

### Run per-file review on changed source files

1. Get the list of changed source files (skip binaries):
   ```
   git diff --name-only HEAD | grep -E '\.(py|ts|tsx|js|jsx)$'
   git diff --cached --name-only | grep -E '\.(py|ts|tsx|js|jsx)$'
   ```

2. For each file, run (suppress JVM warnings to stderr so JSON is clean):
   ```
   "$CS" review --file-name <basename.ext> <filepath> --output-format json 2>/dev/null
   ```

3. Parse the JSON output. Each result has:
   - `score`: Code Health score (0-10, higher is better)
   - `file-level-code-smells`: Array of file-wide issues
   - `function-level-code-smells`: Array with per-function issues, each containing:
     - `function`: Function name
     - `range`: Start/end lines
     - `code-smells`: Array of `{category, details}` objects

   Categories include: `Large Method`, `Complex Method`, `Bumpy Road Ahead`, `Deep Nested Complexity`, `Brain Method`, `Code Duplication`, `Low Cohesion`, `Many Function Arguments`

4. Flag any file with score < 7.0 or any function with `Brain Method` or `Deep Nested Complexity`.

### Custom rules

The project has `.codescene/code-health-rules.json` with path-specific thresholds:
- `scripts/**` — relaxed (pipeline runners)
- `src/fusion/features/**` — relaxed method size (transform chains)
- `src/fusion/validators/**` — relaxed complexity (many conditionals by design)
- `frontend/e2e/**`, `tests/**` — disabled (test code)
- `src/fusion/core_training/**`, `frontend/src/app/**`, `frontend/src/components/**` — full strictness

## Layer 2: cubic (AI Semantic Review)

### Setup

1. Check installed: `which cubic`
   - If not found: `curl -fsSL https://cubic.dev/install | bash`
   - Then authenticate: `cubic auth`

2. **CRITICAL: Error detection.** cubic silently returns `{"issues": []}` on API failures.
   The `--print-logs --log-level ERROR` flags go AFTER the `review` subcommand (they are subcommand options).
   Always capture stderr and check for:
   - `subscription_expired` — tell user to check their cubic plan on Vercel or run `cubic auth login`
   - `403` or `401` — authentication/subscription issue
   - `APIError` — API failure

   The review ONLY counts as successful if stderr contains NO error lines.

### Run the review

```bash
# --print-logs and --log-level are subcommand options, go AFTER 'review'
cubic review --print-logs --log-level ERROR -j \
  -p "Python 3.11 + FastAPI + Next.js + AutoGluon project. ZL soybean oil futures forecasting. 11 specialist signal generators. Focus on: security (SQL injection, secrets in code, exposed API keys), logic errors in forecasting/ML code, API endpoint bugs, React component issues, type safety, missing error handling. Ignore binary model files (.pkl)." \
  2>/tmp/cubic-review-stderr.txt

# Check for silent failures
if grep -qiE '(subscription_expired|APIError|API Auth Error|status=40[13])' /tmp/cubic-review-stderr.txt; then
  echo "CUBIC REVIEW FAILED — check /tmp/cubic-review-stderr.txt"
fi
```

For uncommitted changes: `cubic review --print-logs --log-level ERROR -j -p "..."`
For branch review: `cubic review --print-logs --log-level ERROR -b -j -p "..."`

**Note:** cubic is billed through Vercel marketplace. The Open Source plan covers this public repo with unlimited reviews. If subscription_expired appears, the CLI auth token may need re-linking: `cubic auth logout && cubic auth login`.

### Parse the JSON output

The output contains an `issues` array. Each issue has:
- `priority`: P0 (critical), P1 (high), P2 (medium), P3 (low)
- `file`: File path
- `line`: Line number
- `title`: Issue title
- `description`: Detailed explanation

## Combined Presentation

Present results in two sections:

### Section 1: Code Health (CodeScene)

Show a table of files with their scores and smells:
```
| File | Score | Issues |
|------|-------|--------|
| build_matrix.py | 2.77 | run(): cc=64, 352 lines, Bumpy Road |
```

Flag anything below 7.0 as needing attention. Below 5.0 is critical.

### Section 2: AI Review (cubic)

Group by priority (P0 first, then P1, P2, P3):
```
1. P0 — SQL injection in route.ts:45
2. P1 — Missing null check in pressure_engine.py:120
```

If cubic failed silently, clearly state: "cubic review failed (auth/subscription issue) — only CodeScene results available."

### Offer to fix

After presenting all issues from both tools, offer to fix them. For each:
- Read the file and surrounding context
- Validate the issue is real — skip false positives with explanation
- Fix in the simplest way without refactoring unrelated code
- For CodeScene structural issues: only fix if the user explicitly asks (these often require intentional refactoring)
