-- CreateTable: supply.eia_biodiesel_1w
-- Weekly EIA biodiesel + renewable diesel production (KBPD)
CREATE TABLE IF NOT EXISTS "supply"."eia_biodiesel_1w" (
    "id" SERIAL NOT NULL,
    "week_ending" DATE NOT NULL,
    "biodiesel_production_kbpd" DOUBLE PRECISION,
    "renewable_diesel_production_kbpd" DOUBLE PRECISION,
    "total_biofuel_production_kbpd" DOUBLE PRECISION,
    "source" VARCHAR(50) DEFAULT 'eia_weekly',
    "row_hash" VARCHAR(64) NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "eia_biodiesel_1w_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "eia_biodiesel_1w_week_ending_key" ON "supply"."eia_biodiesel_1w"("week_ending");

-- CreateIndex
CREATE UNIQUE INDEX "eia_biodiesel_1w_row_hash_key" ON "supply"."eia_biodiesel_1w"("row_hash");
