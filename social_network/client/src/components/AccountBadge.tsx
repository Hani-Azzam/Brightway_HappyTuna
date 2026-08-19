import type { AccountType } from '../types';

const MAP: Partial<Record<AccountType, { icon: string; label: string }>> = {
  official: { icon: '✓', label: 'Official account' },
  journalist: { icon: '📰', label: 'Journalist' },
  influencer: { icon: '★', label: 'Influencer' },
};

export function AccountBadge({ accountType }: { accountType: AccountType }) {
  const badge = MAP[accountType];
  if (!badge) return null;
  return (
    <span className={`badge ${accountType}`} title={badge.label} aria-label={badge.label}>
      {badge.icon}
    </span>
  );
}
