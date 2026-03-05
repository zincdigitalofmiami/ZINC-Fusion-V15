import "dotenv/config";
import { defineConfig } from "prisma/config";

const prismaDatasourceUrl =
  process.env.DIRECT_DATABASE_URL ||
  process.env.POSTGRES_URL ||
  process.env.DATABASE_URL;
if (!prismaDatasourceUrl) {
  throw new Error(
    "Prisma datasource URL missing. Set DIRECT_DATABASE_URL or POSTGRES_URL (preferred), or DATABASE_URL.",
  );
}
if (prismaDatasourceUrl.startsWith("prisma+postgres://")) {
  throw new Error(
    "Prisma CLI requires a direct postgres:// URL for migrations/status. Set DIRECT_DATABASE_URL or POSTGRES_URL to a direct connection string.",
  );
}

export default defineConfig({
  schema: "../prisma/schema.prisma",
  migrations: {
    path: "../prisma/migrations",
  },
  datasource: {
    url: prismaDatasourceUrl,
    shadowDatabaseUrl:
      process.env.SHADOW_DATABASE_URL ||
      "postgresql://zincdigital@localhost:5432/zinc_fusion_v15_shadow",
  },
});
