import Anthropic from '@anthropic-ai/sdk';
import { PrismaClient } from '@prisma/client';
import { config } from '../config';
import { logger } from '../utils/logger';
import { isAiAnalysisEnabled } from '../analytics/settings';
import { Analysis, ASPECTS, detectCompany, labelFor, lexiconAnalyze } from '../analytics/lexicon';

const prisma = new PrismaClient();

export type Engine = 'lexicon' | 'claude';

const MODEL = 'claude-haiku-4-5-20251001';

/** The engine that will be used right now: Claude only when the toggle is on AND a key is present. */
export function activeEngine(): Engine {
  return isAiAnalysisEnabled() && config.anthropicApiKey ? 'claude' : 'lexicon';
}

function clampScore(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(-1, Math.min(1, n));
}

async function claudeAnalyze(text: string): Promise<Analysis> {
  const client = new Anthropic({ apiKey: config.anthropicApiKey });
  const aspectKeys = ASPECTS.map((a) => a.key).join(', ');
  const prompt =
    `You analyze public sentiment about the tuna company "${config.companyName}".\n` +
    `Return ONLY minified JSON: {"sentiment": <number -1..1>, "mentionsCompany": <boolean>, ` +
    `"aspects": {<aspectKey>: <number -1..1>}}.\n` +
    `Use only these aspect keys, and include only those the post actually discusses: ${aspectKeys}.\n` +
    `Post: """${text}"""`;

  const res = await client.messages.create({
    model: MODEL,
    max_tokens: 200,
    messages: [{ role: 'user', content: prompt }],
  });

  const block = res.content[0];
  const raw = block && block.type === 'text' ? block.text : '';
  const parsed = JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1)) as {
    sentiment?: unknown;
    mentionsCompany?: unknown;
    aspects?: Record<string, unknown>;
  };

  const score = clampScore(parsed.sentiment);
  const aspects: Record<string, number> = {};
  if (parsed.aspects && typeof parsed.aspects === 'object') {
    for (const [key, value] of Object.entries(parsed.aspects)) {
      if (ASPECTS.some((a) => a.key === key)) aspects[key] = clampScore(value);
    }
  }

  return {
    sentimentScore: score,
    sentimentLabel: labelFor(score),
    aspects,
    mentionsCompany: typeof parsed.mentionsCompany === 'boolean' ? parsed.mentionsCompany : detectCompany(text),
  };
}

/**
 * Analyzes a single piece of text with the active engine. Claude failures fall back to the lexicon.
 */
export async function analyzeText(text: string): Promise<Analysis & { engine: Engine }> {
  if (activeEngine() === 'claude') {
    try {
      return { ...(await claudeAnalyze(text)), engine: 'claude' };
    } catch (err) {
      logger.warn({ err }, 'Claude analysis failed; falling back to lexicon');
      return { ...lexiconAnalyze(text), engine: 'lexicon' };
    }
  }
  return { ...lexiconAnalyze(text), engine: 'lexicon' };
}

export interface AnalyzeResult {
  analyzed: number;
  engine: Engine;
}

/**
 * On-demand batch analysis. By default only analyzes posts that have never been analyzed;
 * pass `reanalyze` to recompute every post (e.g. after switching the engine on/off).
 */
export async function analyzePosts(reanalyze = false): Promise<AnalyzeResult> {
  const posts = await prisma.post.findMany({
    where: reanalyze ? {} : { analyzedAt: null },
    select: { id: true, content: true },
  });

  let analyzed = 0;
  let engine: Engine = activeEngine();
  for (const post of posts) {
    const result = await analyzeText(post.content);
    engine = result.engine;
    await prisma.post.update({
      where: { id: post.id },
      data: {
        sentimentScore: result.sentimentScore,
        sentimentLabel: result.sentimentLabel,
        aspects: JSON.stringify(result.aspects),
        mentionsCompany: result.mentionsCompany,
        analyzedAt: new Date(),
        analyzedBy: result.engine,
      },
    });
    analyzed++;
  }

  return { analyzed, engine };
}

export interface AnalysisStatus {
  aiAnalysisEnabled: boolean;
  hasApiKey: boolean;
  activeEngine: Engine;
  totalPosts: number;
  analyzedPosts: number;
}

/** Current toggle/engine state plus analysis coverage, for the dashboard's control panel. */
export async function getAnalysisStatus(): Promise<AnalysisStatus> {
  const [totalPosts, analyzedPosts] = await Promise.all([
    prisma.post.count(),
    prisma.post.count({ where: { analyzedAt: { not: null } } }),
  ]);
  return {
    aiAnalysisEnabled: isAiAnalysisEnabled(),
    hasApiKey: Boolean(config.anthropicApiKey),
    activeEngine: activeEngine(),
    totalPosts,
    analyzedPosts,
  };
}
