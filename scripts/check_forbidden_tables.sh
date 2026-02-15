#!/bin/bash
# ZINC-FUSION-V15 Schema Guardrail
# Prevents phantom table references from re-entering active code paths
#
# Usage:
#   bash scripts/check_forbidden_tables.sh
#
# Returns:
#   Exit 0 if clean
#   Exit 1 if forbidden references found

echo "==================================================================="
echo "ZINC-FUSION-V15 Schema Guardrail Check"
echo "==================================================================="
echo ""

# Forbidden table patterns
FORBIDDEN_TABLES=(
  "alt\.news_1d"
  "features\.news_sentiment_1d"
  "raw\.fred_observations"
  "raw\.legislation_federal_register"
  "raw\.news"
  "raw\.weather"
  "raw\.market"
  "gold\.[a-z]"
  "silver\.[a-z]"
  "bronze\.[a-z]"
  "monitoring\.[a-z]"
)

VIOLATIONS_FOUND=0

echo "Checking active code paths for forbidden table references..."
echo ""

for pattern in "${FORBIDDEN_TABLES[@]}"; do
  echo "  Checking pattern: $pattern"

  # Check only active code directories (explicit paths, exclude deprecated)
  MATCHES=$(
    grep -rn --include="*.py" --include="*.ts" --include="*.js" -E "$pattern" \
      src/ frontend/src/ scripts/*.{py,ts,js} grafana/ 2>/dev/null | \
    grep -v "DEPRECATED" | \
    grep -v "Deprecated" | \
    grep -v "migrated from" | \
    grep -v "MIGRATED" | \
    grep -v "Previously read from" | \
    grep -v "renamed to" | \
    grep -v "no longer exist" | \
    grep -v "was removed" | \
    grep -v "needs monitoring" | \
    grep -v "Deprecated tables" || true
  )

  if [ -n "$MATCHES" ]; then
    echo "    VIOLATION FOUND:"
    echo "$MATCHES" | while IFS= read -r line; do
      echo "       $line"
    done
    echo ""
    VIOLATIONS_FOUND=1
  else
    echo "    Clean"
  fi
done

echo ""
echo "==================================================================="

if [ $VIOLATIONS_FOUND -eq 1 ]; then
  echo "SCHEMA GUARDRAIL FAILED"
  echo ""
  echo "Forbidden table references found in active code."
  echo ""
  echo "Forbidden tables:"
  echo "  - alt.news_1d (split into alt.policy_news_event, alt.executive_actions_event, alt.econ_news_event, alt.profarmer_news_event)"
  echo "  - features.news_sentiment_1d (removed - no Prisma model; use alt news tables with specialist_tags)"
  echo "  - raw.* (raw schema banned per v2 architecture)"
  echo "  - gold.*, silver.*, bronze.* (medallion schemas banned)"
  echo "  - monitoring.* (banned schema)"
  echo ""
  echo "Fix violations before committing."
  echo "==================================================================="
  exit 1
else
  echo "SCHEMA GUARDRAIL PASSED"
  echo ""
  echo "No forbidden table references found in active code paths."
  echo "==================================================================="
  exit 0
fi
