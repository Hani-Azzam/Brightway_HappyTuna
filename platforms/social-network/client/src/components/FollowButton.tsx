import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';

export function FollowButton({ userId, onAuthRequired }: { userId: string; onAuthRequired: () => void }) {
  const { session, isFollowing, follow, unfollow } = useAuth();
  const [busy, setBusy] = useState(false);

  if (session?.user.id === userId) return null;
  const following = isFollowing(userId);

  async function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!session) {
      onAuthRequired();
      return;
    }
    setBusy(true);
    try {
      if (following) await unfollow(userId);
      else await follow(userId);
    } catch {
      // ignore — state stays as it was
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className={`follow-btn ${following ? 'following' : ''}`} disabled={busy} onClick={toggle}>
      {following ? 'Following' : 'Follow'}
    </button>
  );
}
