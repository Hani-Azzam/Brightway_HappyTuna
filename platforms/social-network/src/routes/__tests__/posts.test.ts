import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { createApp } from '../../server';

const app = createApp();
const prisma = new PrismaClient();

let token: string;
const auth = () => ({ Authorization: `Bearer ${token}` });

beforeEach(async () => {
  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.postHashtag.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.hashtag.deleteMany();
  await prisma.user.deleteMany();

  const res = await request(app).post('/api/auth/login').send({ name: 'poster' });
  token = res.body.data.token;
});

afterAll(async () => {
  await prisma.$disconnect();
});

async function makePost(content: string, repostOfId?: string) {
  const res = await request(app).post('/api/posts').set(auth()).send({ content, repostOfId });
  return res.body.data.post;
}

describe('GET /api/posts', () => {
  it('returns an empty feed when there are no posts', async () => {
    const res = await request(app).get('/api/posts');
    expect(res.status).toBe(200);
    expect(res.body.data.posts).toEqual([]);
  });

  it('includes engagement counts on posts', async () => {
    await makePost('counted post');
    const res = await request(app).get('/api/posts');
    expect(res.body.data.posts[0]._count).toEqual({ likes: 0, reposts: 0, comments: 0 });
  });
});

describe('GET /api/posts/:id', () => {
  it('returns a single post (public)', async () => {
    const post = await makePost('A specific post');
    const res = await request(app).get(`/api/posts/${post.id}`);
    expect(res.status).toBe(200);
    expect(res.body.data.post.content).toBe('A specific post');
  });

  it('returns 404 for an unknown post', async () => {
    const res = await request(app).get('/api/posts/nonexistent-id');
    expect(res.status).toBe(404);
  });
});

describe('POST /api/posts', () => {
  it('creates a post when authenticated', async () => {
    const res = await request(app).post('/api/posts').set(auth()).send({ content: 'Hello BrightWay!' });
    expect(res.status).toBe(201);
    expect(res.body.data.post.content).toBe('Hello BrightWay!');
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).post('/api/posts').send({ content: 'unauthorized' });
    expect(res.status).toBe(401);
  });

  it('returns 400 on missing content', async () => {
    const res = await request(app).post('/api/posts').set(auth()).send({});
    expect(res.status).toBe(400);
  });

  it('creates a quote-post referencing the original', async () => {
    const original = await makePost('original take');
    const res = await request(app)
      .post('/api/posts')
      .set(auth())
      .send({ content: 'great point!', repostOfId: original.id });
    expect(res.status).toBe(201);
    expect(res.body.data.post.repostOf.id).toBe(original.id);
  });

  it('returns 404 when quoting a non-existent post', async () => {
    const res = await request(app)
      .post('/api/posts')
      .set(auth())
      .send({ content: 'quote', repostOfId: 'nope' });
    expect(res.status).toBe(404);
  });
});

describe('likes', () => {
  it('likes (201), rejects duplicate (409), and unlikes (200)', async () => {
    const post = await makePost('likeable');
    expect((await request(app).post(`/api/posts/${post.id}/like`).set(auth())).status).toBe(201);
    expect((await request(app).post(`/api/posts/${post.id}/like`).set(auth())).status).toBe(409);
    expect((await request(app).delete(`/api/posts/${post.id}/like`).set(auth())).status).toBe(200);
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).post('/api/posts/anything/like');
    expect(res.status).toBe(401);
  });
});

describe('reposts', () => {
  it('reposts (201) and unreposts (200)', async () => {
    const post = await makePost('repostable');
    expect((await request(app).post(`/api/posts/${post.id}/repost`).set(auth())).status).toBe(201);
    expect((await request(app).delete(`/api/posts/${post.id}/repost`).set(auth())).status).toBe(200);
  });

  it('returns 404 when reposting a missing post', async () => {
    const res = await request(app).post('/api/posts/nope/repost').set(auth());
    expect(res.status).toBe(404);
  });

  it('amplifies a reposted post onto the reposter profile with viewer state', async () => {
    // A different user authors the original post.
    const authorRes = await request(app).post('/api/auth/login').send({ name: 'orig-author' });
    const authorToken = authorRes.body.data.token as string;
    const authored = await request(app)
      .post('/api/posts')
      .set({ Authorization: `Bearer ${authorToken}` })
      .send({ content: 'please amplify me' });
    const postId = authored.body.data.post.id as string;

    // The authenticated user (token == their id) reposts it.
    await request(app).post(`/api/posts/${postId}/repost`).set(auth());

    // It now appears on the reposter's own profile timeline, labeled, with viewer state set.
    const profile = await request(app).get(`/api/users/${token}/posts`).set(auth());
    const entry = profile.body.data.posts.find((p: { id: string }) => p.id === postId);
    expect(entry).toBeTruthy();
    expect(entry.reposter.id).toBe(token);
    expect(entry.viewerHasReposted).toBe(true);
  });

  it('reports viewer repost state on the global feed, and false when anonymous', async () => {
    const post = await makePost('mine to repost');
    await request(app).post(`/api/posts/${post.id}/repost`).set(auth());

    const authed = await request(app).get('/api/posts').set(auth());
    const mine = authed.body.data.posts.find((p: { id: string }) => p.id === post.id);
    expect(mine.viewerHasReposted).toBe(true);

    const anon = await request(app).get('/api/posts');
    const anonPost = anon.body.data.posts.find((p: { id: string }) => p.id === post.id);
    expect(anonPost.viewerHasReposted).toBe(false);
    expect(anonPost.viewerHasLiked).toBe(false);
  });
});

describe('comments', () => {
  it('creates a comment when authenticated', async () => {
    const post = await makePost('A post to comment on');
    const res = await request(app)
      .post(`/api/posts/${post.id}/comments`)
      .set(auth())
      .send({ content: 'Great post!' });
    expect(res.status).toBe(201);
    expect(res.body.data.comment.content).toBe('Great post!');
  });

  it('returns 401 without a token', async () => {
    const res = await request(app).post('/api/posts/some-id/comments').send({ content: 'Not allowed' });
    expect(res.status).toBe(401);
  });

  it('lists comments for a post (public)', async () => {
    const post = await makePost('Post with comments');
    await request(app).post(`/api/posts/${post.id}/comments`).set(auth()).send({ content: 'Comment 1' });
    const res = await request(app).get(`/api/posts/${post.id}/comments`);
    expect(res.status).toBe(200);
    expect(res.body.data.comments).toHaveLength(1);
  });
});
