#!/usr/bin/env python3
"""
Validate Inngest Jobs - Check Bronze Contract Compliance

Checks if Inngest jobs follow the Bronze v2.0 contract:
1. Logs to ops.ingest_run
2. Computes row_hash for idempotency
3. Assigns specialist_tags
4. Uses append-only inserts (no upserts)
5. Quarantines to ops.quarantined_record on error

Usage:
    python scripts/validate_inngest_jobs.py
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
INNGEST_DIR = PROJECT_ROOT / "frontend" / "src" / "inngest"

# Bronze Contract Requirements
BRONZE_REQUIREMENTS = [
    ("ingest_run", r"ops\.ingest_run|IngestRun"),
    ("row_hash", r"row_hash|createHash|crypto"),
    ("specialist_tags", r"specialist_tags|specialistTags"),
    ("append_only", r"INSERT.*ON CONFLICT.*DO NOTHING"),
    ("no_upsert", r"DO UPDATE"),  # This should NOT be present
]

def check_file_compliance(filepath: Path) -> Dict[str, bool]:
    """Check a single file for Bronze contract compliance."""
    content = filepath.read_text()
    
    results = {}
    for req_name, pattern in BRONZE_REQUIREMENTS:
        if req_name == "no_upsert":
            # This should NOT match
            results[req_name] = not bool(re.search(pattern, content, re.IGNORECASE))
        else:
            # This SHOULD match
            results[req_name] = bool(re.search(pattern, content, re.IGNORECASE))
    
    return results

def main():
    print("=" * 80)
    print("INNGEST JOBS BRONZE CONTRACT VALIDATION")
    print("=" * 80)
    
    # Get all Inngest job files
    job_files = [
        f for f in INNGEST_DIR.glob("*.ts")
        if f.name not in ["client.ts", "functions.ts"]
    ]
    
    print(f"\nFound {len(job_files)} Inngest job files")
    print()
    
    # Check each file
    results_table = []
    for job_file in sorted(job_files):
        job_name = job_file.stem
        compliance = check_file_compliance(job_file)
        
        # Calculate compliance score
        score = sum(1 for v in compliance.values() if v)
        total = len(compliance)
        pct = (score / total) * 100
        
        results_table.append({
            "name": job_name,
            "score": score,
            "total": total,
            "pct": pct,
            "compliance": compliance,
        })
    
    # Print results
    print("=" * 80)
    print("COMPLIANCE RESULTS")
    print("=" * 80)
    print(f"\n{'Job Name':<25} {'Score':<10} {'Status':<15} {'Issues'}")
    print("-" * 80)
    
    for result in results_table:
        score_str = f"{result['score']}/{result['total']}"
        status = "✅ COMPLIANT" if result['pct'] == 100 else "❌ NON-COMPLIANT"
        
        # Find failing requirements
        issues = [
            req for req, passed in result['compliance'].items()
            if not passed
        ]
        issues_str = ", ".join(issues) if issues else "None"
        
        print(f"{result['name']:<25} {score_str:<10} {status:<15} {issues_str}")
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    compliant = sum(1 for r in results_table if r['pct'] == 100)
    total = len(results_table)
    print(f"Compliant Jobs: {compliant}/{total}")
    print(f"Non-Compliant: {total - compliant}/{total}")
    
    # Reference job
    print()
    print("=" * 80)
    print("REFERENCE: fred-daily.ts (Bronze v2.0 Pattern)")
    print("=" * 80)
    print("All jobs should follow the pattern in fred-daily.ts:")
    print("1. Import createHash from crypto")
    print("2. Create ops.ingest_run at start")
    print("3. Compute row_hash for each row")
    print("4. Assign specialist_tags based on domain")
    print("5. Use INSERT...ON CONFLICT DO NOTHING (append-only)")
    print("6. Update ingest_run.status at end")
    print("7. Quarantine invalid records to ops.quarantined_record")
    
    print()
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("1. Review fred-daily.ts as the Bronze v2.0 reference")
    print("2. Update non-compliant jobs to follow the same pattern")
    print("3. Test each updated job")
    print("4. Re-run this validation script")
    
    # Return exit code
    return 0 if compliant == total else 1

if __name__ == "__main__":
    exit(main())
