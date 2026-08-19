import { Express } from 'express';
import { createMcpHttpRouter } from './httpTransport';
import { createSocialMcpServer } from './socialServer';
import { createAnalyticsMcpServer } from './analyticsServer';

/**
 * Mounts the two MCP servers as Streamable-HTTP endpoints on the existing Express app:
 * - `/mcp/social`    — participation tools (post, engage, follow, browse).
 * - `/mcp/analytics` — research tools over the sentiment-analytics layer.
 *
 * Each endpoint manages its own sessions and builds a fresh MCP server per connecting client, so no
 * separate process or port is needed — the endpoints ride the same server the API and web app use.
 */
export function mountMcp(app: Express): void {
  app.use('/mcp/social', createMcpHttpRouter(createSocialMcpServer));
  app.use('/mcp/analytics', createMcpHttpRouter(createAnalyticsMcpServer));
}
