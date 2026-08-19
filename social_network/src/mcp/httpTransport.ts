import { randomUUID } from 'crypto';
import express, { Router, Request, Response } from 'express';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { isInitializeRequest } from '@modelcontextprotocol/sdk/types.js';
import { logger } from '../utils/logger';

/**
 * Builds an Express router that speaks the MCP Streamable-HTTP protocol for a family of MCP servers.
 *
 * Each client connection is a session: an `initialize` POST (with no session header) mints a new
 * session id, builds a fresh `McpServer` via `makeServer` (giving that session its own isolated
 * state), and connects it to a per-session transport. Subsequent POST/GET/DELETE requests carrying
 * the `mcp-session-id` header are routed to the matching transport. GET opens the SSE stream and
 * DELETE tears the session down.
 *
 * The parent Express app already applies `express.json()`, so the parsed body is passed straight to
 * `transport.handleRequest(req, res, req.body)` (the SDK's documented pattern for Express).
 *
 * @param makeServer factory invoked once per new session to create that session's MCP server.
 */
export function createMcpHttpRouter(makeServer: () => McpServer): Router {
  const router = express.Router();
  const transports = new Map<string, StreamableHTTPServerTransport>();

  router.post('/', async (req: Request, res: Response) => {
    const sessionId = req.headers['mcp-session-id'] as string | undefined;

    let transport = sessionId ? transports.get(sessionId) : undefined;

    if (!transport && !sessionId && isInitializeRequest(req.body)) {
      transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (id: string) => {
          transports.set(id, transport!);
        },
      });
      transport.onclose = () => {
        if (transport!.sessionId) transports.delete(transport!.sessionId);
      };
      const server = makeServer();
      await server.connect(transport);
    } else if (!transport) {
      res.status(400).json({
        jsonrpc: '2.0',
        error: { code: -32000, message: 'Bad Request: no valid session id, and not an initialize request' },
        id: null,
      });
      return;
    }

    try {
      await transport.handleRequest(req, res, req.body);
    } catch (err) {
      logger.error({ err }, 'MCP POST handling failed');
      if (!res.headersSent) res.status(500).end();
    }
  });

  // GET opens the server-to-client SSE stream; DELETE ends the session. Both require a live session.
  const handleSessionRequest = async (req: Request, res: Response): Promise<void> => {
    const sessionId = req.headers['mcp-session-id'] as string | undefined;
    const transport = sessionId ? transports.get(sessionId) : undefined;
    if (!transport) {
      res.status(400).send('Invalid or missing session id');
      return;
    }
    try {
      await transport.handleRequest(req, res);
    } catch (err) {
      logger.error({ err }, 'MCP session request handling failed');
      if (!res.headersSent) res.status(500).end();
    }
  };

  router.get('/', handleSessionRequest);
  router.delete('/', handleSessionRequest);

  return router;
}
