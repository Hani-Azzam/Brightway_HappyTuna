import { PrismaClient } from '@prisma/client';
import { attachViewerState, createPost, getGlobalFeed, getPostById, getTimeline } from '../postService';
import { AppError } from '../../utils/errors';

const prisma = new PrismaClient();
const page = { skip: 0, take: 20 };

function createUser(name: string) {
  return prisma.user.create({ data: { name } });
}

/** Creates a post with a fixed timestamp so ordering assertions are deterministic. */
function createPostAt(userId: string, content: string, at: Date) {
  return prisma.post.create({ data: { userId, content, createdAt: at } });
}

/** Records a repost with a fixed timestamp. */
function repostAt(userId: string, postId: string, at: Date) {
  return prisma.repost.create({ data: { userId, postId, createdAt: at } });
}

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.user.deleteMany();
});

afterAll(async () => {
  await prisma.$disconnect();
});

describe('createPost', () => {
  it('creates a post and returns it with author info', async () => {
    const u = await createUser('poster');
    const post = await createPost(u.id, 'Hello world!');
    expect(post.content).toBe('Hello world!');
    expect(post.user.name).toBe('poster');
  });

  it('throws 400 on empty content', async () => {
    const u = await createUser('empty');
    await expect(createPost(u.id, '   ')).rejects.toThrow(AppError);
  });

  it('throws 400 when content exceeds 500 chars', async () => {
    const u = await createUser('toolong');
    await expect(createPost(u.id, 'a'.repeat(501))).rejects.toThrow(AppError);
  });
});

describe('getGlobalFeed', () => {
  it('returns posts newest first', async () => {
    const u = await createUser('feeduser');
    await createPost(u.id, 'First');
    await createPost(u.id, 'Second');
    const feed = await getGlobalFeed(page);
    expect(feed[0]!.content).toBe('Second');
    expect(feed[1]!.content).toBe('First');
  });
});

describe('getPostById', () => {
  it('returns a post with comments', async () => {
    const u = await createUser('findpost');
    const post = await createPost(u.id, 'Find me');
    const found = await getPostById(post.id);
    expect(found.content).toBe('Find me');
  });

  it('reports the viewer like/repost state', async () => {
    const author = await createUser('pauthor');
    const viewer = await createUser('pviewer');
    const post = await createPost(author.id, 'engage with me');
    await prisma.like.create({ data: { userId: viewer.id, postId: post.id } });

    const asViewer = await getPostById(post.id, viewer.id);
    expect(asViewer.viewerHasLiked).toBe(true);
    expect(asViewer.viewerHasReposted).toBe(false);

    const asAnon = await getPostById(post.id);
    expect(asAnon.viewerHasLiked).toBe(false);
  });

  it('throws 404 for a non-existent post', async () => {
    await expect(getPostById('nonexistent')).rejects.toThrow(AppError);
  });
});

describe('getTimeline', () => {
  it('returns an empty array when there are no authors', async () => {
    expect(await getTimeline([], page)).toEqual([]);
  });

  it('surfaces a followed account\'s repost as an amplified entry with a reposter label', async () => {
    const author = await createUser('origin');
    const amplifier = await createUser('amplifier');
    const post = await createPostAt(author.id, 'crisis update', new Date('2026-07-01T10:00:00Z'));
    await repostAt(amplifier.id, post.id, new Date('2026-07-01T12:00:00Z'));

    // Feed of someone who follows only the amplifier (not the author).
    const timeline = await getTimeline([amplifier.id], page);
    expect(timeline).toHaveLength(1);
    expect(timeline[0]!.id).toBe(post.id);
    expect(timeline[0]!.content).toBe('crisis update');
    expect(timeline[0]!.reposter?.id).toBe(amplifier.id);
  });

  it('labels an original post with no reposter', async () => {
    const author = await createUser('solo');
    await createPostAt(author.id, 'just me', new Date('2026-07-01T10:00:00Z'));
    const timeline = await getTimeline([author.id], page);
    expect(timeline[0]!.reposter ?? null).toBeNull();
  });

  it('de-dupes a post shown as both original and repost, keeping the most recent surfacing', async () => {
    const author = await createUser('dedupe-author');
    const amplifier = await createUser('dedupe-amp');
    const post = await createPostAt(author.id, 'reach', new Date('2026-07-01T10:00:00Z'));
    await repostAt(amplifier.id, post.id, new Date('2026-07-01T15:00:00Z'));

    // Following BOTH the author and the amplifier: the post must appear once, at the repost surfacing.
    const timeline = await getTimeline([author.id, amplifier.id], page);
    expect(timeline).toHaveLength(1);
    expect(timeline[0]!.reposter?.id).toBe(amplifier.id);
  });

  it('orders originals and reposts together by surfaced time, newest first', async () => {
    const author = await createUser('mixed');
    const other = await createUser('other');
    await createPostAt(author.id, 'older', new Date('2026-07-01T10:00:00Z'));
    const external = await createPostAt(other.id, 'external', new Date('2026-07-01T09:00:00Z'));
    await createPostAt(author.id, 'newer', new Date('2026-07-01T14:00:00Z'));
    await repostAt(author.id, external.id, new Date('2026-07-01T12:00:00Z'));

    const timeline = await getTimeline([author.id], page);
    expect(timeline.map((p) => p.content)).toEqual(['newer', 'external', 'older']);
    expect(timeline[1]!.reposter?.id).toBe(author.id); // the external post is surfaced via repost
  });
});

describe('attachViewerState', () => {
  it('flags the viewer\'s own likes and reposts, and defaults to false for others', async () => {
    const author = await createUser('vs-author');
    const viewer = await createUser('vs-viewer');
    const liked = await createPost(author.id, 'liked post');
    const reposted = await createPost(author.id, 'reposted post');
    const untouched = await createPost(author.id, 'untouched post');
    await prisma.like.create({ data: { userId: viewer.id, postId: liked.id } });
    await prisma.repost.create({ data: { userId: viewer.id, postId: reposted.id } });

    const [l, r, u] = await attachViewerState([liked, reposted, untouched], viewer.id);
    expect(l!.viewerHasLiked).toBe(true);
    expect(r!.viewerHasReposted).toBe(true);
    expect(u!.viewerHasLiked).toBe(false);
    expect(u!.viewerHasReposted).toBe(false);
  });

  it('returns all-false when there is no viewer', async () => {
    const author = await createUser('vs-anon');
    const post = await createPost(author.id, 'anon view');
    const [view] = await attachViewerState([post]);
    expect(view!.viewerHasLiked).toBe(false);
    expect(view!.viewerHasReposted).toBe(false);
  });
});
