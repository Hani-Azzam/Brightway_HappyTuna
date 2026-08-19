export type AccountType = 'regular' | 'influencer' | 'journalist' | 'official';

export interface Meta {
  platformName: string;
  companyName: string;
}

export interface UserSummary {
  id: string;
  name: string;
  avatar: string | null;
  accountType: AccountType;
}

export interface User extends UserSummary {
  bio: string | null;
  createdAt: string;
}

export interface UserWithCounts extends User {
  _count: { posts: number; followers: number; following: number };
}

export interface Comment {
  id: string;
  content: string;
  postId: string;
  userId: string;
  createdAt: string;
  user: UserSummary;
}

export interface Post {
  id: string;
  content: string;
  userId: string;
  repostOfId: string | null;
  createdAt: string;
  user: UserSummary;
  repostOf: Post | null;
  comments: Comment[];
  _count: { likes: number; reposts: number; comments: number };
  // Set when this post appears in a timeline because `reposter` reposted it (pure amplification).
  reposter?: UserSummary | null;
  // Whether the requesting user has liked / reposted this post (present on authenticated reads).
  viewerHasLiked?: boolean;
  viewerHasReposted?: boolean;
}

export interface TrendingTag {
  tag: string;
  count: number;
}

export interface Session {
  token: string;
  user: User;
}

export interface SearchResults {
  users: UserSummary[];
  posts: Post[];
  hashtags: { id: string; tag: string }[];
}

export type Engine = 'lexicon' | 'claude';

export interface AnalysisConfig {
  aiAnalysisEnabled: boolean;
  hasApiKey: boolean;
  activeEngine: Engine;
  totalPosts: number;
  analyzedPosts: number;
}

export interface Overview {
  opinionIndex: number;
  weightedOpinionIndex: number;
  sentiment: { positive: number; neutral: number; negative: number };
  shareOfVoice: number;
  crisisMeter: number;
  totals: { posts: number; analyzed: number; companyMentions: number };
}

export interface TimelineBucket {
  bucket: string;
  volume: number;
  positive: number;
  neutral: number;
  negative: number;
  opinionIndex: number;
}

export interface AspectStat {
  key: string;
  label: string;
  volume: number;
  sentiment: number;
}

export interface TrendStat {
  tag: string;
  count: number;
  previous: number;
  rising: number;
  sentiment: number;
}

export interface Influencer {
  id: string;
  name: string;
  accountType: AccountType;
  followers: number;
  repostsReceived: number;
  influence: number;
  stance: number | null;
}

export interface Spike {
  bucket: string;
  volume: number;
  zScore: number;
  sentiment: number;
}

export interface TopPost {
  post: Post;
  engagement: number;
}

export interface CohortStat {
  key: string;
  label: string;
  posts: number;
  authors: number;
  opinionIndex: number;
  positive: number;
  neutral: number;
  negative: number;
}

export interface CohortReport {
  byType: CohortStat[];
  shapers: CohortStat;
  publicVoice: CohortStat;
  official: CohortStat;
  gap: number;
}

export interface Narrative {
  tag: string;
  posts: number;
  authors: number;
  sentiment: number;
  origin: 'shaper' | 'official' | 'grassroots';
  originator: { id: string; name: string; accountType: AccountType } | null;
  firstSeen: string;
  lastSeen: string;
  byType: { regular: number; influencer: number; journalist: number; official: number };
}
