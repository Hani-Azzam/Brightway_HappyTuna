const mockCreate = jest.fn();
jest.mock('@anthropic-ai/sdk', () => ({
  __esModule: true,
  default: jest.fn().mockImplementation(() => ({ messages: { create: mockCreate } })),
}));

import { PrismaClient } from '@prisma/client';
import { analyzeText, analyzePosts, getAnalysisStatus, activeEngine } from '../sentimentService';
import { setAiAnalysisEnabled } from '../../analytics/settings';

const prisma = new PrismaClient();

function createUser(name: string) {
  return prisma.user.create({ data: { name } });
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
  setAiAnalysisEnabled(false);
  delete process.env['ANTHROPIC_API_KEY'];
  mockCreate.mockReset();
});

afterAll(async () => {
  setAiAnalysisEnabled(false);
  delete process.env['ANTHROPIC_API_KEY'];
  await prisma.$disconnect();
});

describe('lexicon engine (default)', () => {
  it('uses the lexicon when AI analysis is off', async () => {
    const a = await analyzeText('Love this fresh BrightWay tuna #brightway');
    expect(a.engine).toBe('lexicon');
    expect(a.sentimentLabel).toBe('positive');
    expect(a.mentionsCompany).toBe(true);
  });
});

describe('analyzePosts', () => {
  it('analyzes only unanalyzed posts, then reanalyzes on demand', async () => {
    const u = await createUser('p');
    await prisma.post.create({ data: { userId: u.id, content: 'Love BrightWay #brightway' } });

    const first = await analyzePosts();
    expect(first.analyzed).toBe(1);
    expect(first.engine).toBe('lexicon');

    const post = await prisma.post.findFirst();
    expect(post!.analyzedAt).not.toBeNull();
    expect(post!.mentionsCompany).toBe(true);

    expect((await analyzePosts()).analyzed).toBe(0);
    expect((await analyzePosts(true)).analyzed).toBe(1);
  });
});

describe('getAnalysisStatus', () => {
  it('reports coverage and toggle state', async () => {
    const u = await createUser('p');
    await prisma.post.create({ data: { userId: u.id, content: 'hi' } });
    await analyzePosts();

    const status = await getAnalysisStatus();
    expect(status.totalPosts).toBe(1);
    expect(status.analyzedPosts).toBe(1);
    expect(status.aiAnalysisEnabled).toBe(false);
    expect(status.activeEngine).toBe('lexicon');
  });
});

describe('claude engine', () => {
  it('uses Claude when enabled with a key and parses its JSON', async () => {
    process.env['ANTHROPIC_API_KEY'] = 'test-key';
    setAiAnalysisEnabled(true);
    expect(activeEngine()).toBe('claude');

    mockCreate.mockResolvedValue({
      content: [{ type: 'text', text: '{"sentiment":0.9,"mentionsCompany":true,"aspects":{"taste":0.9}}' }],
    });

    const a = await analyzeText('whatever');
    expect(a.engine).toBe('claude');
    expect(a.sentimentLabel).toBe('positive');
    expect(a.aspects['taste']).toBe(0.9);
    expect(mockCreate).toHaveBeenCalled();
  });

  it('falls back to the lexicon when Claude throws', async () => {
    process.env['ANTHROPIC_API_KEY'] = 'test-key';
    setAiAnalysisEnabled(true);
    mockCreate.mockRejectedValue(new Error('boom'));

    const a = await analyzeText('Love fresh BrightWay tuna');
    expect(a.engine).toBe('lexicon');
    expect(a.sentimentLabel).toBe('positive');
  });
});
