import type { AccountType } from '../types';

export function Avatar({
  avatar,
  accountType,
  size = 40,
}: {
  avatar: string | null;
  accountType?: AccountType;
  size?: 40 | 48 | 64;
}) {
  const ring = accountType && accountType !== 'regular' ? `ring-${accountType}` : '';
  return (
    <div className={`avatar sz-${size} ${ring}`} aria-hidden="true">
      {avatar || '🐟'}
    </div>
  );
}
