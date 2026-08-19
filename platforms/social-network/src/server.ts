import express from 'express';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import swaggerUi from 'swagger-ui-express';
import metaRouter from './routes/meta';
import authRouter from './routes/auth';
import usersRouter from './routes/users';
import postsRouter from './routes/posts';
import hashtagsRouter from './routes/hashtags';
import searchRouter from './routes/search';
import analyticsRouter from './routes/analytics';
import { errorHandler } from './middleware/errorHandler';
import { mountMcp } from './mcp/mount';
import { config } from './config';

/**
 * Creates and configures the Express application.
 */
export function createApp(): express.Application {
  const app = express();

  app.use(cors({ origin: config.corsOrigin }));
  app.use(express.json());
  app.use(express.static(path.join(__dirname, '..', 'public')));

  // Interactive API docs (Swagger UI) at /openapi, backed by the maintained spec at /openapi.json.
  // The spec carries an operationId per endpoint, so it also drives client codegen and agent/MCP tooling.
  const openapiFile = path.join(__dirname, '..', 'public', 'openapi.json');
  if (fs.existsSync(openapiFile)) {
    const spec = JSON.parse(fs.readFileSync(openapiFile, 'utf-8'));
    app.use('/openapi', swaggerUi.serve, swaggerUi.setup(spec, { customSiteTitle: 'BrightTweets API' }));
  }

  // The React app lives under /app; send the bare site root there.
  app.get('/', (_req, res) => res.redirect('/app/'));

  app.use('/api/meta', metaRouter);
  app.use('/api/auth', authRouter);
  app.use('/api/users', usersRouter);
  app.use('/api/posts', postsRouter);
  app.use('/api/hashtags', hashtagsRouter);
  app.use('/api/search', searchRouter);
  app.use('/api/analytics', analyticsRouter);

  // MCP servers for AI agents: /mcp/social (participation) and /mcp/analytics (research).
  mountMcp(app);

  // SPA fallback: serve the built React client (public/app) for client-side routes under /app.
  app.get('/app/*', (_req, res, next) => {
    const indexFile = path.join(__dirname, '..', 'public', 'app', 'index.html');
    if (fs.existsSync(indexFile)) res.sendFile(indexFile);
    else next();
  });

  app.use(errorHandler);

  return app;
}
