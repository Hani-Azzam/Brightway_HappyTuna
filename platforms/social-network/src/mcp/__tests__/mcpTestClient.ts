import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { CallToolResult } from '@modelcontextprotocol/sdk/types.js';

/**
 * Connects an in-memory MCP client to a freshly built server over a linked transport pair.
 * Lets the MCP tests exercise the real tool-dispatch path without any HTTP.
 */
export async function connectToServer(server: McpServer): Promise<Client> {
  const client = new Client({ name: 'mcp-test-client', version: '1.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  return client;
}

/** Returns the first text content block of a tool result, or throws if there isn't one. */
export function textOf(result: CallToolResult): string {
  const block = result.content[0];
  if (!block || block.type !== 'text') throw new Error('tool result has no text content');
  return block.text;
}

/** Parses the JSON payload a successful tool returns in its text block. */
export function jsonOf<T = unknown>(result: CallToolResult): T {
  return JSON.parse(textOf(result)) as T;
}
