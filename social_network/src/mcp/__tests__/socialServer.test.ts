import { PrismaClient } from '@prisma/client';
import { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { createSocialMcpServer } from '../socialServer';
import { connectToServer, jsonOf } from './mcpTestClient';

const prisma = new PrismaClient();

/** Calls a tool and returns the normalized MCP result. */
async function call(client: Client, name: string, args: Record<string, unknown> = {}): Promise<CallToolResult> {
  return (await client.callTool({ name, arguments: args })) as CallToolResult;
}

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.postHashtag.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.hashtag.deleteMany();
  await prisma.user.deleteMany();
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('social MCP server', () => {
  it('lists the participation tools', async () => {
    const client = await connectToServer(createSocialMcpServer());
    const { tools } = await client.listTools();
    const names = tools.map((t) => t.name);
    expect(names).toEqual(expect.arrayContaining(['login', 'create_post', 'like_post', 'get_global_feed', 'search']));
  });

  it('login binds the session so a created post appears in the global feed', async () => {
    const client = await connectToServer(createSocialMcpServer());

    const login = jsonOf<{ token: string; user: { name: string } }>(await call(client, 'login', { name: 'bot-alice' }));
    expect(login.user.name).toBe('bot-alice');

    const posted = jsonOf<{ id: string; content: string }>(
      await call(client, 'create_post', { content: 'Fresh tuna is #delicious' }),
    );
    expect(posted.content).toBe('Fresh tuna is #delicious');

    const feed = jsonOf<Array<{ id: string }>>(await call(client, 'get_global_feed', {}));
    expect(feed.map((p) => p.id)).toContain(posted.id);
  });

  it('rejects a write tool before login with a clean error', async () => {
    const client = await connectToServer(createSocialMcpServer());
    const res = await call(client, 'create_post', { content: 'no identity yet' });
    expect(res.isError).toBe(true);
    expect(jsonErrorText(res)).toMatch(/Not logged in/i);
  });

  it('surfaces a service AppError (empty content) as a tool error', async () => {
    const client = await connectToServer(createSocialMcpServer());
    await call(client, 'login', { name: 'bot-bob' });
    const res = await call(client, 'create_post', { content: '   ' });
    expect(res.isError).toBe(true);
    expect(jsonErrorText(res)).toMatch(/Error 400/);
  });

  it('supports engagement: like then unlike a post', async () => {
    const client = await connectToServer(createSocialMcpServer());
    await call(client, 'login', { name: 'bot-liker' });
    const post = jsonOf<{ id: string }>(await call(client, 'create_post', { content: 'like me' }));

    const liked = jsonOf<{ message: string }>(await call(client, 'like_post', { postId: post.id }));
    expect(liked.message).toBe('Liked');

    const unliked = jsonOf<{ message: string }>(await call(client, 'unlike_post', { postId: post.id }));
    expect(unliked.message).toBe('Unliked');
  });

  it('isolates identity per session (a second server has no logged-in user)', async () => {
    const a = await connectToServer(createSocialMcpServer());
    await call(a, 'login', { name: 'session-a' });

    const b = await connectToServer(createSocialMcpServer());
    const res = await call(b, 'create_post', { content: 'from b' });
    expect(res.isError).toBe(true);
  });

  it('exercises the full participation toolset end to end', async () => {
    const client = await connectToServer(createSocialMcpServer());

    const meta = jsonOf<{ platformName: string }>(await call(client, 'get_meta'));
    expect(typeof meta.platformName).toBe('string');

    const me = jsonOf<{ token: string }>(await call(client, 'login', { name: 'graph-owner' }));
    const other = jsonOf<{ token: string; user: { id: string } }>(await call(client, 'login', { name: 'graph-target' }));
    const targetId = other.user.id;
    // log back in as the first user (login rebinds this session's identity)
    await call(client, 'login', { name: 'graph-owner' });

    const post = jsonOf<{ id: string }>(await call(client, 'create_post', { content: 'Great #tuna today' }));
    const comment = jsonOf<{ id: string }>(await call(client, 'add_comment', { postId: post.id, content: 'agreed' }));
    expect(comment.id).toBeTruthy();

    expect(jsonOf<{ message: string }>(await call(client, 'repost_post', { postId: post.id })).message).toBe('Reposted');
    expect(jsonOf<{ message: string }>(await call(client, 'unrepost_post', { postId: post.id })).message).toBe('Unreposted');
    expect(jsonOf<{ message: string }>(await call(client, 'follow_user', { targetId })).message).toMatch(/Followed/);
    expect(jsonOf<{ message: string }>(await call(client, 'unfollow_user', { targetId })).message).toMatch(/Unfollowed/);

    const updated = jsonOf<{ accountType: string }>(await call(client, 'set_account_type', { accountType: 'influencer' }));
    expect(updated.accountType).toBe('influencer');

    // read tools
    expect(Array.isArray(jsonOf(await call(client, 'get_my_feed')))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_global_feed')))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'list_users')))).toBe(true);
    expect(jsonOf<{ id: string }>(await call(client, 'get_user', { id: me.token })).id).toBe(me.token);
    expect(Array.isArray(jsonOf(await call(client, 'get_user_posts', { id: me.token })))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_following', { id: me.token })))).toBe(true);
    expect(jsonOf<{ id: string }>(await call(client, 'get_post', { id: post.id })).id).toBe(post.id);
    expect(Array.isArray(jsonOf(await call(client, 'get_comments', { postId: post.id })))).toBe(true);
    expect(jsonOf<{ posts: unknown[] }>(await call(client, 'search', { q: 'tuna' })).posts).toBeDefined();
    expect(Array.isArray(jsonOf(await call(client, 'get_trending_hashtags', { limit: 5 })))).toBe(true);
    expect(Array.isArray(jsonOf(await call(client, 'get_hashtag_posts', { tag: '#tuna' })))).toBe(true);

    // quote-post referencing the original
    const quote = jsonOf<{ repostOfId: string | null }>(
      await call(client, 'create_post', { content: 'quoting this', repostOfId: post.id }),
    );
    expect(quote.repostOfId).toBe(post.id);
  });
});

/** The error text carried by an `isError` tool result. */
function jsonErrorText(result: CallToolResult): string {
  const block = result.content[0];
  return block && block.type === 'text' ? block.text : '';
}
