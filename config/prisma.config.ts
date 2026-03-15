import { defineConfig } from "prisma/config";

const prismaDatasourceUrl = process.env.DATABASE_URL;
if (!prismaDatasourceUrl) {
  throw new Error(
    "Prisma datasource URL missing. Set DATABASE_URL.",
  );
}
if (prismaDatasourceUrl.startsWith("prisma+postgres://")) {
  throw new Error(
    "Prisma CLI requires a direct postgres:// URL for migrations/status. Set DATABASE_URL to a direct connection string.",
  );
}

const expectedShadowDbName =
  process.env.SHADOW_DB_EXPECTED_NAME || "zinc_fusion_v15_shadow";
const shadowDatabaseUrl =
  process.env.SHADOW_DATABASE_URL ||
  "postgresql://zincdigital@localhost:5432/zinc_fusion_v15_shadow";

let resolvedShadowDbName = "";
try {
  const parsed = new URL(shadowDatabaseUrl);
  resolvedShadowDbName = parsed.pathname.replace(/^\/+/, "");
} catch {
  throw new Error(
    "SHADOW_DATABASE_URL is invalid. Provide a valid postgres:// URL for the Prisma shadow database.",
  );
}

if (resolvedShadowDbName !== expectedShadowDbName) {
  throw new Error(
    `Shadow DB mismatch. Expected database '${expectedShadowDbName}', got '${resolvedShadowDbName}'. Update SHADOW_DATABASE_URL.`,
  );
}

export default defineConfig({
  schema: "../prisma/schema.prisma",
  migrations: {
    path: "../prisma/migrations",
  },
  datasource: {
    url: prismaDatasourceUrl,
    shadowDatabaseUrl,
  },
});
