import path from 'node:path'
import { config } from 'dotenv'
import { defineConfig } from 'prisma/config'

// Load .env from project root, not cwd
const projectRoot = path.resolve(__dirname, '..')
config({ path: path.join(projectRoot, '.env') })

export default defineConfig({
  earlyAccess: true,
  schema: path.join(__dirname, 'schema.prisma'),

  datasource: {
    url: process.env.DATABASE_URL!,
  },

  migrate: {
    async url() {
      return process.env.DATABASE_URL!
    },
  },
})
