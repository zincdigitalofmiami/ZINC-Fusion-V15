# DATABASE TRUTH

## THERE IS ONLY ONE DATABASE

**Prisma Postgres** - that's it. Nothing else.

- Connection: `DATABASE_URL` in `.env`
- Schema: `prisma/schema.prisma`

## THERE IS NO

- Local database
- DuckDB
- MotherDuck
- Second database

## DEPLOYMENT

- Frontend: Vercel (Next.js + Inngest)
- Database: Prisma Postgres (cloud-hosted)

## BEFORE EDITING ANY DATABASE-RELATED CODE

1. Query the actual database to verify table/column exists
2. Check `prisma/schema.prisma` for the model definition
3. Confirm the schema matches reality

## ZL IS THE ONLY INTRADAY INSTRUMENT

- `analytics.zl_live` - ZL live price (single row)
- `analytics.zl_intraday` - ZL 15m bars

There are NO generic `intraday_prices` or `latest_prices` tables for multiple symbols.
