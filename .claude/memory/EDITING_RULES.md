# EDITING RULES

## BEFORE ANY EDIT

1. Read the entire file
2. Understand what it does
3. Verify against database if it's DB-related
4. Propose the change to the user
5. Wait for explicit approval

## NEVER EDIT WITHOUT APPROVAL

- `prisma/schema.prisma`
- Any config file
- `.env` files
- `AGENTS.md`
- `CLAUDE.md`

## NEVER DELETE WITHOUT APPROVAL

- Any file
- Any database table
- Any code that might be used elsewhere

## MINIMAL CHANGES

- Change only what is necessary
- Do not refactor surrounding code
- Do not add "improvements"
- Do not clean up unrelated issues

## ACCURACY OVER SPEED

From CLAUDE.md:
> "You always prioritize accuracy over speed."
> "Speed and pleasing the user is not your objective."

Take time. Read first. Verify. Then act.
