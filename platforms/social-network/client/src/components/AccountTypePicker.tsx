import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import type { AccountType } from '../types';

const OPTIONS: Array<{ value: AccountType; label: string }> = [
  { value: 'regular', label: 'Regular' },
  { value: 'influencer', label: '★ Influencer' },
  { value: 'journalist', label: '📰 Journalist' },
  { value: 'official', label: '✓ Official' },
];

/**
 * Self-service role picker on your own profile. In the simulation the bot team designates shapers;
 * this lets a human (or a bot acting as itself) set its own account type so the analytics light up.
 */
export function AccountTypePicker({ value, onChanged }: { value: AccountType; onChanged: (next: AccountType) => void }) {
  const { setAccountType } = useAuth();
  const [saving, setSaving] = useState(false);

  const change = async (next: AccountType) => {
    if (next === value || saving) return;
    setSaving(true);
    try {
      await setAccountType(next);
      onChanged(next);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="type-picker">
      <span className="type-picker-label">Account role</span>
      <div className="type-picker-opts">
        {OPTIONS.map((o) => (
          <button
            key={o.value}
            className={`type-opt ${o.value === value ? 'active' : ''}`}
            disabled={saving}
            onClick={() => change(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
