import 'dotenv/config'
import path from 'node:path'
import { defineConfig, env } from 'prisma/config'

export default defineConfig({
  earlyAccess: true,
  schema: path.join(__dirname, 'schema.prisma'),

  datasource: {
    url: env('DATABASE_URL'),
  },

  migrate: {
    async url() {
      return process.env.DATABASE_URL!
    },
  },
})
