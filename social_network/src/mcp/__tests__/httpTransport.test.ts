import { Server } from 'http';
import { AddressInfo } from 'net';
import { PrismaClient } from '@prisma/client';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { createApp } from '../../server';

const prisma = new PrismaClient();
let server: Server;
let baseUrl: string;

beforeAll(async () => {
  await new Promise<void>((resolve) => {
    server = createApp().listen(0, () => {
      const { port } = server.address() as AddressInfo;
      baseUrl = `http://127.0.0.1:${port}`;
      resolve();
    });
  });
});

afterAll(async () => {
  await prisma.$disconnect();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

beforeEach(async () => {
  await prisma.post.deleteMany();
  await prisma.user.deleteMany();
});

/** Connects a real Streamable-HTTP MCP client to one of the mounted endpoints. */
async function connect(path: string): Promise<Client> {
  const client = new Client({ name: 'http-test-client', version: '1.0.0' });
  await client.connect(new StreamableHTTPClientTransport(new URL(`${baseUrl}${path}`)));
  return client;
}

describe('MCP over Streamable HTTP', () => {
  it('initializes a session and lists tools on /mcp/social', async () => {
    const client = await connect('/mcp/social');
    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name)).toContain('create_post');
    await client.close();
  });

  it('drives a login + create_post flow over HTTP and persists it', async () => {
    const client = await connect('/mcp/social');
    await client.callTool({ name: 'login', arguments: { name: 'http-bot' } });
    const res = (await client.callTool({
      name: 'create_post',
      arguments: { content: 'posted over http' },
    })) as CallToolResult;
    expect(res.isError).toBeFalsy();

    const count = await prisma.post.count();
    expect(count).toBe(1);
    await client.close();
  });

  it('serves the analytics endpoint too', async () => {
    const client = await connect('/mcp/analytics');
    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name)).toContain('get_overview');
    await client.close();
  });

  it('rejects a non-initialize POST without a session id (400)', async () => {
    const res = await fetch(`${baseUrl}/mcp/social`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 }),
    });
    expect(res.status).toBe(400);
  });

  it('rejects a GET without a session id (400)', async () => {
    const res = await fetch(`${baseUrl}/mcp/social`, {
      method: 'GET',
      headers: { Accept: 'text/event-stream' },
    });
    expect(res.status).toBe(400);
  });
});
