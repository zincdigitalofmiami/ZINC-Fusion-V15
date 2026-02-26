-- CreateIndex
CREATE INDEX "idx_legislation_1d_event_date" ON "alt"."legislation_1d" ("event_date" DESC);

-- CreateIndex
CREATE INDEX "idx_legislation_1d_tags" ON "alt"."legislation_1d" USING GIN ("specialist_tags");
