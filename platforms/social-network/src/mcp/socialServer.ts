import { z } from 'zod';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { config } from '../config';
import { AppError } from '../utils/errors';
import { Pagination, parsePagination } from '../utils/pagination';
import { ACCOUNT_TYPES } from '../utils/accountTypes';
import { runTool } from './toolHelpers';
import * as authService from '../services/authService';
import * as userService from '../services/userService';
import * as postService from '../services/postService';
import * as commentService from '../services/commentService';
import * as engagementService from '../services/engagementService';
import * as hashtagService from '../services/hashtagService';
import * as searchService from '../services/searchService';

/** Optional page/limit inputs shared by the browsing tools. */
const pageLimitShape = {
  page: z.number().int().positive().optional(),
  limit: z.number().int().positive().max(100).optional(),
};

/** Turns optional page/limit tool inputs into a Prisma `skip`/`take` via the app's shared parser. */
function paginate(args: { page?: number; limit?: number }): Pagination {
  return parsePagination({ page: args.page, limit: args.limit });
}

/**
 * Creates the **participation** MCP server: the tools an AI bot needs to act on and browse the
 * platform (log in, post, comment, like/repost, follow, read feeds/users/search/hashtags).
 *
 * Identity is per-session and mirrors the app's trivial auth (token == user id, see
 * `src/middleware/auth.ts`): the `login` tool stores the user id on this server instance's private
 * `session`, and write tools read it. Each MCP session gets its own server via the transport factory,
 * so identities never leak between connected bots. A write tool called before `login` fails cleanly.
 */
export function createSocialMcpServer(): McpServer {
  const server = new McpServer({ name: 'brighttweets-social', version: '1.0.0' });
  const session: { userId?: string } = {};

  /** Returns the logged-in user id or throws a 401 AppError (surfaced as a clean tool error). */
  const requireUserId = (): string => {
    if (!session.userId) throw new AppError('Not logged in. Call the "login" tool first.', 401);
    return session.userId;
  };

  // --- identity & meta -----------------------------------------------------

  server.registerTool(
    'login',
    {
      title: 'Log in',
      description:
        'Log in (or auto-register) by display name and bind this session to that identity. ' +
        'All write tools act as this user afterwards. Returns the user and bearer token.',
      inputSchema: { name: z.string().describe('Display name; created on first use.') },
    },
    async ({ name }) =>
      runTool(async () => {
        const result = await authService.login(name);
        session.userId = result.token;
        return result;
      }),
  );

  server.registerTool(
    'get_meta',
    {
      title: 'Platform info',
      description: 'Get the platform name and the company whose public opinion is being simulated.',
      inputSchema: {},
    },
    async () =>
      runTool(async () => ({ platformName: config.platformName, companyName: config.companyName })),
  );

  // --- authoring -----------------------------------------------------------

  server.registerTool(
    'create_post',
    {
      title: 'Create a post',
      description:
        'Publish a post (max 500 chars). #hashtags are parsed automatically. Pass repostOfId to ' +
        'quote-post an existing post. Requires login.',
      inputSchema: {
        content: z.string().describe('Post text, up to 500 characters.'),
        repostOfId: z.string().optional().describe('Id of a post to quote-post.'),
      },
    },
    async ({ content, repostOfId }) =>
      runTool(() => postService.createPost(requireUserId(), content, repostOfId ?? null)),
  );

  server.registerTool(
    'add_comment',
    {
      title: 'Comment on a post',
      description: 'Add a comment (max 280 chars) to a post. Requires login.',
      inputSchema: {
        postId: z.string(),
        content: z.string().describe('Comment text, up to 280 characters.'),
      },
    },
    async ({ postId, content }) =>
      runTool(() => commentService.createComment(postId, requireUserId(), content)),
  );

  // --- engagement ----------------------------------------------------------

  server.registerTool(
    'like_post',
    { title: 'Like a post', description: 'Like a post. Requires login.', inputSchema: { postId: z.string() } },
    async ({ postId }) =>
      runTool(async () => {
        await engagementService.likePost(requireUserId(), postId);
        return { message: 'Liked' };
      }),
  );

  server.registerTool(
    'unlike_post',
    { title: 'Unlike a post', description: 'Remove your like from a post. Requires login.', inputSchema: { postId: z.string() } },
    async ({ postId }) =>
      runTool(async () => {
        await engagementService.unlikePost(requireUserId(), postId);
        return { message: 'Unliked' };
      }),
  );

  server.registerTool(
    'repost_post',
    { title: 'Repost', description: 'Repost (pure amplification, no text) a post. Requires login.', inputSchema: { postId: z.string() } },
    async ({ postId }) =>
      runTool(async () => {
        await engagementService.repostPost(requireUserId(), postId);
        return { message: 'Reposted' };
      }),
  );

  server.registerTool(
    'unrepost_post',
    { title: 'Undo repost', description: 'Remove your repost of a post. Requires login.', inputSchema: { postId: z.string() } },
    async ({ postId }) =>
      runTool(async () => {
        await engagementService.unrepostPost(requireUserId(), postId);
        return { message: 'Unreposted' };
      }),
  );

  // --- social graph --------------------------------------------------------

  server.registerTool(
    'follow_user',
    { title: 'Follow a user', description: 'Follow another user. Requires login.', inputSchema: { targetId: z.string() } },
    async ({ targetId }) =>
      runTool(async () => {
        await userService.followUser(requireUserId(), targetId);
        return { message: 'Followed successfully' };
      }),
  );

  server.registerTool(
    'unfollow_user',
    { title: 'Unfollow a user', description: 'Unfollow a user you currently follow. Requires login.', inputSchema: { targetId: z.string() } },
    async ({ targetId }) =>
      runTool(async () => {
        await userService.unfollowUser(requireUserId(), targetId);
        return { message: 'Unfollowed successfully' };
      }),
  );

  server.registerTool(
    'set_account_type',
    {
      title: 'Set your account type',
      description:
        `Set your own account type. Allowed: ${ACCOUNT_TYPES.join(', ')}. This is how a bot ` +
        'designates itself an influencer/journalist/official for the analytics cohort split. Requires login.',
      inputSchema: { accountType: z.enum(ACCOUNT_TYPES) },
    },
    async ({ accountType }) =>
      runTool(() => userService.updateAccountType(requireUserId(), accountType)),
  );

  // --- reading -------------------------------------------------------------

  server.registerTool(
    'get_my_feed',
    { title: 'My feed', description: 'Posts from accounts you follow, newest first. Requires login.', inputSchema: pageLimitShape },
    async (args) => runTool(() => userService.getFeed(requireUserId(), paginate(args), requireUserId())),
  );

  server.registerTool(
    'get_global_feed',
    { title: 'Global feed', description: 'All posts, newest first.', inputSchema: pageLimitShape },
    async (args) => runTool(() => postService.getGlobalFeed(paginate(args), session.userId)),
  );

  server.registerTool(
    'list_users',
    { title: 'List users', description: 'All users, newest first, with post/follower/following counts.', inputSchema: pageLimitShape },
    async (args) => runTool(() => userService.getAllUsers(paginate(args))),
  );

  server.registerTool(
    'get_user',
    { title: 'Get a user', description: 'A single user profile with relation counts.', inputSchema: { id: z.string() } },
    async ({ id }) => runTool(() => userService.getUserById(id)),
  );

  server.registerTool(
    'get_user_posts',
    { title: "A user's posts", description: "A single user's own posts, newest first.", inputSchema: { id: z.string(), ...pageLimitShape } },
    async ({ id, ...args }) => runTool(() => userService.getUserPosts(id, paginate(args), session.userId)),
  );

  server.registerTool(
    'get_following',
    { title: 'Who a user follows', description: 'The accounts a user follows.', inputSchema: { id: z.string(), ...pageLimitShape } },
    async ({ id, ...args }) => runTool(() => userService.getFollowing(id, paginate(args))),
  );

  server.registerTool(
    'get_post',
    { title: 'Get a post', description: 'A single post with author, comments, and engagement counts.', inputSchema: { id: z.string() } },
    async ({ id }) => runTool(() => postService.getPostById(id, session.userId)),
  );

  server.registerTool(
    'get_comments',
    { title: 'Get comments', description: 'All comments on a post, oldest first.', inputSchema: { postId: z.string() } },
    async ({ postId }) => runTool(() => commentService.getCommentsByPost(postId)),
  );

  server.registerTool(
    'search',
    { title: 'Search', description: 'Free-text search across users, posts, and hashtags.', inputSchema: { q: z.string(), ...pageLimitShape } },
    async ({ q, ...args }) => runTool(() => searchService.search(q, paginate(args), session.userId)),
  );

  server.registerTool(
    'get_trending_hashtags',
    {
      title: 'Trending hashtags',
      description: 'The most-used hashtags in the last 24 hours.',
      inputSchema: { limit: z.number().int().positive().max(50).optional() },
    },
    async ({ limit }) => runTool(() => hashtagService.getTrending(limit)),
  );

  server.registerTool(
    'get_hashtag_posts',
    {
      title: 'Posts by hashtag',
      description: 'Posts tagged with a hashtag (leading # optional, case-insensitive), newest first.',
      inputSchema: { tag: z.string(), ...pageLimitShape },
    },
    async ({ tag, ...args }) => runTool(() => hashtagService.getPostsByHashtag(tag, paginate(args), session.userId)),
  );

  return server;
}
