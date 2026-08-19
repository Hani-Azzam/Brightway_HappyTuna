import { PrismaClient } from '@prisma/client';
import { config } from '../src/config';
import { extractHashtags } from '../src/utils/text';

const prisma = new PrismaClient();

// Everything company-specific is derived from config.companyName, so the demo always matches
// whatever COMPANY_NAME is set to (no brand is hardcoded in the scenario).
const COMPANY = config.companyName; // display name, e.g. "HappyTuna"
const TAG = COMPANY.replace(/\s+/g, ''); // hashtag stem, e.g. "HappyTuna" -> #HappyTuna
const OFFICIAL = `${COMPANY.toLowerCase().replace(/\s+/g, '')}_official`; // e.g. "happytuna_official"

/**
 * Demo scenario — a staggered narrative arc so the analytics dashboard has movement to show
 * (a falling Opinion Index, a Crisis-Meter response, a volume spike, a shaper-led narrative, and a
 * journalist-vs-public cohort gap). The arc, in order:
 *
 *   1. Calm baseline (~3 days ago): the company announces pole-and-line; creators & press praise it.
 *   2. A journalist breaks a mercury concern (~28h ago) — the origin of the #<company>mercury narrative.
 *   3. Influencers amplify it (~26–22h ago).
 *   4. The public reacts in a burst (~12h ago) — a deliberate volume spike.
 *   5. The company responds (~3h ago).
 *
 * Post times are set via `hoursAgo` so timelines, spike detection, and the Crisis Meter all light up.
 * Used for local development and the analytics dashboard; not loaded by the test suite.
 */
const users = [
  { name: OFFICIAL, accountType: 'official', avatar: '🏢', bio: `Official account of ${COMPANY}. Sustainably sourced since 1998.` },
  { name: 'maria_chen', accountType: 'journalist', avatar: '📰', bio: 'Reporter @ Ocean Beat. Covering seafood & sustainability.' },
  { name: 'the_daily_catch', accountType: 'journalist', avatar: '🗞️', bio: 'Food-industry news, one bite at a time.' },
  { name: 'finfluencer_sam', accountType: 'influencer', avatar: '🐟', bio: 'Seafood recipes & reviews. 500k hungry followers.' },
  { name: 'eco_warrior_lia', accountType: 'influencer', avatar: '🌊', bio: 'Ocean advocate. Dolphin-safe or nothing.' },
  { name: 'tuna_tom', accountType: 'regular', avatar: '🥪', bio: 'Just a guy who loves a good tuna melt.' },
  { name: 'pantry_pat', accountType: 'regular', avatar: '🛒', bio: 'Budget meals for a family of five.' },
  { name: 'skeptic_sue', accountType: 'regular', avatar: '🧐', bio: "I read the labels so you don't have to." },
  { name: 'hungry_henry', accountType: 'regular', avatar: '🍽️', bio: 'Always snacking.' },
];

interface SeedPost {
  key: string;
  author: string;
  hoursAgo: number;
  content: string;
}

const posts: SeedPost[] = [
  // 1. Calm, positive baseline.
  { key: 'announce', author: OFFICIAL, hoursAgo: 70, content: `Proud to announce every can of ${COMPANY} is now 100% pole-and-line caught. #DolphinSafe #Sustainability #${TAG}` },
  { key: 'eco_praise', author: 'eco_warrior_lia', hoursAgo: 68, content: `Love that @${OFFICIAL} is going pole-and-line. This is what ocean stewardship looks like. 🌊 #DolphinSafe #${TAG}` },
  { key: 'sam_bowl', author: 'finfluencer_sam', hoursAgo: 60, content: `Made a seared ${COMPANY} tuna bowl tonight — fresh, meaty, delicious. Honestly their best product yet. 🐟 #${TAG}` },
  { key: 'tom_melt', author: 'tuna_tom', hoursAgo: 54, content: `${COMPANY} melt hits different. Affordable and tasty. 10/10 lunch.` },
  { key: 'maria_sales', author: 'maria_chen', hoursAgo: 50, content: `${COMPANY} reports record quarterly sales as demand for sustainable seafood climbs. Full story on Ocean Beat. #${TAG}` },

  // 2. A journalist breaks the concern — the origin of the mercury narrative.
  { key: 'maria_mercury', author: 'maria_chen', hoursAgo: 28, content: `Investigation: an independent lab found elevated mercury in several ${COMPANY} tuna batches. The company has not yet responded. #${TAG}Mercury #${TAG}` },

  // 3. Influencers amplify it.
  { key: 'eco_warn', author: 'eco_warrior_lia', hoursAgo: 26, content: `If the mercury reports are true this is a betrayal of everything @${OFFICIAL} promised. Concerned and disappointed. #${TAG}Mercury #DolphinSafe` },
  { key: 'daily_followup', author: 'the_daily_catch', hoursAgo: 24, content: `Following @maria_chen's report — three retailers are now reviewing ${COMPANY} shelf space over the mercury concerns. #${TAG}Mercury #${TAG}` },
  { key: 'sam_pause', author: 'finfluencer_sam', hoursAgo: 22, content: `Hate to post this, but I'm pausing my ${COMPANY} recipes until we get real answers on the mercury testing. 😔 #${TAG}Mercury` },

  // 4. The public reacts in a burst (same hour → a volume spike).
  { key: 'sue_label', author: 'skeptic_sue', hoursAgo: 12, content: `I KNEW something was off. ${COMPANY} tasted saltier and weird for weeks. Reading every label now. 🧐 #${TAG}Mercury` },
  { key: 'pat_kids', author: 'pantry_pat', hoursAgo: 12, content: `I feed ${COMPANY} to my kids every single week. Absolutely shaken by this mercury news. #${TAG}Mercury` },
  { key: 'henry_shock', author: 'hungry_henry', hoursAgo: 12, content: `wait the ${COMPANY} I snack on every day has mercury?? this is gross 😳 #${TAG}Mercury` },
  { key: 'tom_doubt', author: 'tuna_tom', hoursAgo: 12, content: `Bummed about the ${COMPANY} news, that melt was my go-to lunch. Hope it isn't true. #${TAG}Mercury` },
  { key: 'eco_boycott', author: 'eco_warrior_lia', hoursAgo: 12, content: `Officially pulling ${COMPANY} from my pantry until this is independently cleared. #${TAG}Mercury #Boycott` },

  // 5. The company responds.
  { key: 'official_response', author: OFFICIAL, hoursAgo: 3, content: `We take these reports seriously. Independent testing of every ${COMPANY} batch is underway and the results will be published in full. Safety is our top priority. #${TAG}Responds #${TAG}` },
  { key: 'maria_response', author: 'maria_chen', hoursAgo: 2, content: `${COMPANY} says independent testing is underway and results will be public. We will keep following this. #${TAG}Responds #${TAG}Mercury` },
];

const follows: Array<[string, string]> = [
  ['tuna_tom', OFFICIAL],
  ['tuna_tom', 'finfluencer_sam'],
  ['tuna_tom', 'maria_chen'],
  ['pantry_pat', OFFICIAL],
  ['pantry_pat', 'eco_warrior_lia'],
  ['pantry_pat', 'the_daily_catch'],
  ['skeptic_sue', 'maria_chen'],
  ['skeptic_sue', 'the_daily_catch'],
  ['skeptic_sue', 'eco_warrior_lia'],
  ['hungry_henry', 'finfluencer_sam'],
  ['hungry_henry', 'maria_chen'],
  ['hungry_henry', 'eco_warrior_lia'],
  ['eco_warrior_lia', OFFICIAL],
  ['finfluencer_sam', OFFICIAL],
  ['maria_chen', OFFICIAL],
];

const comments: Array<{ post: string; commenter: string; content: string }> = [
  { post: 'announce', commenter: 'eco_warrior_lia', content: 'Finally! Been asking for this for years. 🙌' },
  { post: 'announce', commenter: 'skeptic_sue', content: "Pole-and-line for every can? I'll believe it when I see the certification." },
  { post: 'maria_mercury', commenter: 'skeptic_sue', content: 'Called it. Something always felt off.' },
  { post: 'maria_mercury', commenter: 'tuna_tom', content: "Say it isn't so. This was my lunch every day." },
  { post: 'official_response', commenter: 'eco_warrior_lia', content: 'Too little, too late. Publish the data.' },
  { post: 'official_response', commenter: 'pantry_pat', content: 'Please hurry — I have kids eating this.' },
];

const likes: Array<{ user: string; post: string }> = [
  { user: 'tuna_tom', post: 'announce' },
  { user: 'pantry_pat', post: 'announce' },
  { user: 'eco_warrior_lia', post: 'announce' },
  { user: 'maria_chen', post: 'announce' },
  { user: 'hungry_henry', post: 'sam_bowl' },
  { user: 'tuna_tom', post: 'sam_bowl' },
  // The breaking story draws heavy engagement.
  { user: 'skeptic_sue', post: 'maria_mercury' },
  { user: 'eco_warrior_lia', post: 'maria_mercury' },
  { user: 'hungry_henry', post: 'maria_mercury' },
  { user: 'pantry_pat', post: 'maria_mercury' },
  { user: 'tuna_tom', post: 'maria_mercury' },
  { user: 'skeptic_sue', post: 'eco_boycott' },
];

const reposts: Array<{ user: string; post: string }> = [
  { user: 'eco_warrior_lia', post: 'announce' },
  { user: 'finfluencer_sam', post: 'announce' },
  // The mercury report is amplified widely — this is the propagation footprint.
  { user: 'eco_warrior_lia', post: 'maria_mercury' },
  { user: 'the_daily_catch', post: 'maria_mercury' },
  { user: 'finfluencer_sam', post: 'maria_mercury' },
  { user: 'skeptic_sue', post: 'maria_mercury' },
  { user: 'pantry_pat', post: 'maria_mercury' },
  { user: 'tuna_tom', post: 'maria_mercury' },
  { user: 'hungry_henry', post: 'eco_boycott' },
  { user: 'skeptic_sue', post: 'eco_boycott' },
];

function at(hoursAgo: number): Date {
  return new Date(Date.now() - hoursAgo * 60 * 60 * 1000);
}

async function main(): Promise<void> {
  console.log(`Seeding ${COMPANY} demo scenario (narrative arc)...`);

  await prisma.comment.deleteMany();
  await prisma.like.deleteMany();
  await prisma.repost.deleteMany();
  await prisma.postHashtag.deleteMany();
  await prisma.follow.deleteMany();
  await prisma.post.deleteMany();
  await prisma.hashtag.deleteMany();
  await prisma.user.deleteMany();

  const userIds: Record<string, string> = {};
  for (const u of users) {
    const created = await prisma.user.create({ data: u });
    userIds[u.name] = created.id;
  }

  const postIds: Record<string, string> = {};
  for (const p of posts) {
    const tags = extractHashtags(p.content);
    const created = await prisma.post.create({
      data: {
        userId: userIds[p.author]!,
        content: p.content,
        createdAt: at(p.hoursAgo),
        hashtags: {
          create: tags.map((tag) => ({ hashtag: { connectOrCreate: { where: { tag }, create: { tag } } } })),
        },
      },
    });
    postIds[p.key] = created.id;
  }

  for (const [follower, following] of follows) {
    await prisma.follow.create({ data: { followerId: userIds[follower]!, followingId: userIds[following]! } });
  }

  for (const c of comments) {
    await prisma.comment.create({ data: { postId: postIds[c.post]!, userId: userIds[c.commenter]!, content: c.content } });
  }

  for (const l of likes) {
    await prisma.like.create({ data: { userId: userIds[l.user]!, postId: postIds[l.post]! } });
  }

  for (const r of reposts) {
    await prisma.repost.create({ data: { userId: userIds[r.user]!, postId: postIds[r.post]! } });
  }

  console.log(
    `Done. Seeded ${users.length} users, ${posts.length} posts, ${follows.length} follows, ` +
      `${comments.length} comments, ${likes.length} likes, ${reposts.length} reposts.`,
  );
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
