import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { createApp } from '../../server';
import { setAiAnalysisEnabled } from '../../analytics/settings';

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
  setAiAnalysisEnabled(false);
  delete process.env['ANTHROPIC_API_KEY'];

  const res = await request(app).post('/api/auth/login').send({ name: 'analyst_subject' });
  token = res.body.data.token;
  await request(app).post('/api/posts').set(auth()).send({ content: 'Love fresh BrightWay tuna #brightway' });
  await request(app).post('/api/posts').set(auth()).send({ content: 'BrightWay tuna is gross and a scam #brightway' });
});

afterAll(async () => {
  setAiAnalysisEnabled(false);
  await prisma.$disconnect();
});

describe('GET/PUT /api/analytics/config', () => {
  it('reports the current toggle/engine state', async () => {
    const res = await request(app).get('/api/analytics/config');
    expect(res.status).toBe(200);
    expect(res.body.data.aiAnalysisEnabled).toBe(false);
    expect(res.body.data.activeEngine).toBe('lexicon');
  });

  it('toggles AI analysis on/off', async () => {
    const on = await request(app).put('/api/analytics/config').send({ aiAnalysisEnabled: true });
    expect(on.status).toBe(200);
    expect(on.body.data.aiAnalysisEnabled).toBe(true);
    // no key present, so the active engine is still the lexicon
    expect(on.body.data.activeEngine).toBe('lexicon');
    await request(app).put('/api/analytics/config').send({ aiAnalysisEnabled: false });
  });

  it('rejects an invalid toggle body', async () => {
    const res = await request(app).put('/api/analytics/config').send({ aiAnalysisEnabled: 'yes' });
    expect(res.status).toBe(400);
  });
});

describe('POST /api/analytics/analyze + metrics', () => {
  it('analyzes posts then serves all metric endpoints', async () => {
    const analyze = await request(app).post('/api/analytics/analyze').send({});
    expect(analyze.status).toBe(200);
    expect(analyze.body.data.analyzed).toBe(2);
    expect(analyze.body.data.engine).toBe('lexicon');

    const overview = await request(app).get('/api/analytics/overview');
    expect(overview.status).toBe(200);
    expect(overview.body.data.totals.companyMentions).toBe(2);
    expect(overview.body.data.sentiment.negative).toBe(1);
    expect(typeof overview.body.data.weightedOpinionIndex).toBe('number');

    expect((await request(app).get('/api/analytics/aspects')).body.data.aspects).toHaveLength(6);
    expect(Array.isArray((await request(app).get('/api/analytics/trends')).body.data.trends)).toBe(true);
    expect(Array.isArray((await request(app).get('/api/analytics/influencers')).body.data.influencers)).toBe(true);
    expect(Array.isArray((await request(app).get('/api/analytics/sentiment/timeline')).body.data.timeline)).toBe(true);
    expect(Array.isArray((await request(app).get('/api/analytics/spikes')).body.data.spikes)).toBe(true);
    expect(Array.isArray((await request(app).get('/api/analytics/top-posts')).body.data.posts)).toBe(true);

    const cohorts = await request(app).get('/api/analytics/cohorts');
    expect(cohorts.status).toBe(200);
    expect(cohorts.body.data.byType).toHaveLength(4);
    expect(cohorts.body.data.publicVoice.posts).toBe(2);

    const narratives = await request(app).get('/api/analytics/narratives');
    expect(narratives.status).toBe(200);
    expect(narratives.body.data.narratives.find((n: { tag: string }) => n.tag === 'brightway').origin).toBe('grassroots');
  });
});
