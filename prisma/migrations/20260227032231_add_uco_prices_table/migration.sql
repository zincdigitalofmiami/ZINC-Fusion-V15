-- CreateTable: supply.uco_prices_1w
-- UCO (used cooking oil), yellow grease, tallow pricing from USDA AMS
CREATE TABLE IF NOT EXISTS "supply"."uco_prices_1w" (
    "id" SERIAL NOT NULL,
    "event_date" DATE NOT NULL,
    "product" VARCHAR(100) NOT NULL,
    "region" VARCHAR(100),
    "price_low" DOUBLE PRECISION,
    "price_high" DOUBLE PRECISION,
    "price_avg" DOUBLE PRECISION,
    "unit" VARCHAR(30) DEFAULT 'cents/lb',
    "volume" DOUBLE PRECISION,
    "source" VARCHAR(50) DEFAULT 'usda_ams',
    "row_hash" VARCHAR(64) NOT NULL,
    "knowledge_time" TIMESTAMPTZ(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "uco_prices_1w_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "uco_prices_1w_row_hash_key" ON "supply"."uco_prices_1w"("row_hash");

-- CreateIndex
CREATE UNIQUE INDEX "uco_prices_1w_event_date_product_region_key" ON "supply"."uco_prices_1w"("event_date", "product", "region");
