#!/usr/bin/env bash
# ============================================================================
# ZENFLOW TASK LAUNCHER
# Creates a new SDD task with proper artifact structure
#
# Usage:
#   scripts/zenflow-task.sh "Task title" [workflow]
#
# Examples:
#   scripts/zenflow-task.sh "Add user authentication" full-sdd
#   scripts/zenflow-task.sh "Fix login bug" fix-bug
#   scripts/zenflow-task.sh "Update config file" quick-change
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Arguments
TASK_TITLE="${1:-}"
WORKFLOW="${2:-full-sdd}"

if [[ -z "$TASK_TITLE" ]]; then
    echo -e "${YELLOW}Usage: $0 \"Task title\" [workflow]${NC}"
    echo ""
    echo "Available workflows:"
    echo "  full-sdd     - Spec-Driven Development for complex tasks (default)"
    echo "  fix-bug      - Structured debugging with root cause analysis"
    echo "  quick-change - For simple single-file changes"
    exit 1
fi

# Generate task ID
TASK_ID="task-$(date +%Y%m%d-%H%M%S)"
TASK_DIR=".zenflow/tasks/$TASK_ID"
DATE=$(date +%Y-%m-%d)

echo -e "${BOLD}Creating new Zenflow task...${NC}"
echo ""

# Create task directory
mkdir -p "$TASK_DIR"

# Get workflow file
WORKFLOW_FILE=".zenflow/workflows/${WORKFLOW}.md"
if [[ ! -f "$WORKFLOW_FILE" ]]; then
    echo -e "${YELLOW}Warning: Workflow '$WORKFLOW' not found, using full-sdd${NC}"
    WORKFLOW_FILE=".zenflow/workflows/full-sdd.md"
    WORKFLOW="full-sdd"
fi

# Copy workflow as task instructions
cp "$WORKFLOW_FILE" "$TASK_DIR/WORKFLOW.md"

# Create artifacts based on workflow type
if [[ "$WORKFLOW" == "full-sdd" ]]; then
    # Full SDD needs all three artifacts
    for template in requirements spec plan; do
        TEMPLATE_FILE=".zenflow/templates/${template}.md"
        if [[ -f "$TEMPLATE_FILE" ]]; then
            sed -e "s/{TASK_TITLE}/$TASK_TITLE/g" \
                -e "s/{TASK_ID}/$TASK_ID/g" \
                -e "s/{DATE}/$DATE/g" \
                "$TEMPLATE_FILE" > "$TASK_DIR/${template}.md"
        fi
    done
elif [[ "$WORKFLOW" == "fix-bug" ]]; then
    # Bug fix needs a bug report
    cat > "$TASK_DIR/bug-report.md" << EOF
# Bug Report: $TASK_TITLE

> **Created**: $DATE
> **Task ID**: $TASK_ID

## Reproduction Steps
1. [Step 1]
2. [Step 2]
3. [Expected vs Actual]

## Error Output
\`\`\`
[Paste full stack trace here]
\`\`\`

## Root Cause Analysis

### Failing Location
- **File**: \`[file.py:line]\`
- **Function**: \`[function_name]\`
- **Symptom**: [What goes wrong]

### Root Cause
[Why it fails - not just where]

### Evidence
- Read \`[file:line]\` - found [observation]

---

## Proposed Fix

### Change Summary
[One sentence]

### File(s) to Modify
- \`[file.py:line]\` - [specific change]

### Verification
\`\`\`bash
scripts/verify.sh
\`\`\`
EOF
fi

# Create task manifest
case "$WORKFLOW" in
    full-sdd)
        PHASES_JSON='{
    "requirements": "pending",
    "spec": "pending",
    "plan": "pending",
    "implement": "pending"
  }'
        ;;
    fix-bug)
        PHASES_JSON='{
    "reproduce": "pending",
    "analyze": "pending",
    "fix": "pending"
  }'
        ;;
    quick-change)
        PHASES_JSON='{
    "implement": "pending"
  }'
        ;;
    *)
        PHASES_JSON='{
    "implement": "pending"
  }'
        ;;
esac

cat > "$TASK_DIR/task.json" << EOF
{
  "id": "$TASK_ID",
  "title": "$TASK_TITLE",
  "workflow": "$WORKFLOW",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "created",
  "phases": $PHASES_JSON
}
EOF

# Print summary
echo -e "${GREEN}Task created successfully!${NC}"
echo ""
echo -e "${BOLD}Task Details:${NC}"
echo "  ID:       $TASK_ID"
echo "  Title:    $TASK_TITLE"
echo "  Workflow: $WORKFLOW"
echo "  Location: $TASK_DIR/"
echo ""
echo -e "${BOLD}Artifacts:${NC}"
ls -1 "$TASK_DIR/" | while read f; do echo "  - $f"; done
echo ""
echo -e "${CYAN}${BOLD}Next Steps:${NC}"
if [[ "$WORKFLOW" == "full-sdd" ]]; then
    echo "1. Read: $TASK_DIR/WORKFLOW.md"
    echo "2. Fill out: $TASK_DIR/requirements.md"
    echo "3. Get approval, then proceed to spec.md"
    echo "4. Get approval, then proceed to plan.md"
    echo "5. Get approval, then implement"
elif [[ "$WORKFLOW" == "fix-bug" ]]; then
    echo "1. Reproduce the bug"
    echo "2. Fill out: $TASK_DIR/bug-report.md"
    echo "3. Get root cause approval before fixing"
else
    echo "1. Make your change"
    echo "2. Run: scripts/verify.sh"
fi
echo ""
echo -e "${YELLOW}Remember: scripts/verify.sh must pass before claiming done!${NC}"
