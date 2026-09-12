import { defineConfig } from '@medusajs/framework/utils';

for (const name of ['DATABASE_URL', 'REDIS_URL', 'JWT_SECRET', 'COOKIE_SECRET']) {
  if (!process.env[name]) throw new Error(`Missing ${name}; use the repository's local environment runner.`);
}

module.exports = defineConfig({
  admin: { disable: true },
  projectConfig: {
    databaseUrl: process.env.DATABASE_URL,
    redisUrl: process.env.REDIS_URL,
    http: {
      storeCors: 'http://127.0.0.1:15173',
      adminCors: 'http://127.0.0.1:19000',
      authCors: 'http://127.0.0.1:19000',
      jwtSecret: process.env.JWT_SECRET!,
      cookieSecret: process.env.COOKIE_SECRET!,
    },
  },
});
