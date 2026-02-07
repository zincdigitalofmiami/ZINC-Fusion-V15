# Schema Boundaries (LOCKED)

## Allowed Schemas (12 total)

| Schema | Purpose | Can Modify? |
|--------|---------|-------------|
| `mkt` | Market data (futures, options, FX) | Append only |
| `econ` | Economic data (FRED) | Append only |
| `alt` | Alternative data (news, weather) | Append only |
| `pos` | Positioning (CFTC) | Append only |
| `supply` | Supply/demand (USDA, EPA) | Append only |
| `features` | Feature store | Computed/rebuilt |
| `training` | Training matrices, OOF | Rebuilt on demand |
| `model` | Model registry | Versioned |
| `forecasts` | Predictions | Versioned |
| `analytics` | Dashboard data | Real-time updates |
| `metadata` | Instruments, mappings | Governance only |
| `ops` | Job status, health | System-managed |

## BANNED Schemas

**NEVER create or reference:**
- `raw` / `raw.*`
- `gold` / `gold.*`
- `silver` / `silver.*`
- `bronze` / `bronze.*`
- `monitoring`
- `specialist`
- `weather`
- `archive`

If you see these in code, they are LEGACY and should not be replicated.

## Before ANY Database Reference

1. Open `prisma/schema.prisma`
2. Find the exact table definition
3. Verify the schema prefix matches allowed list
4. Verify column names exist exactly as written

```
✗ BAD:  "We can create a raw.market_data table..."
✓ GOOD: "Using mkt.futures_1d (verified at prisma/schema.prisma:L234)"
```

## Schema Changes Require Approval

If you need to modify schema:
1. STOP immediately
2. Propose the change explicitly
3. Wait for user approval
4. Only then proceed

**No silent schema changes. Ever.**
