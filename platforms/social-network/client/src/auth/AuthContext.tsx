import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, loadSession, saveSession } from '../api/client';
import type { AccountType, Session, User } from '../types';

interface AuthValue {
  session: Session | null;
  user: User | null;
  login: (name: string) => Promise<void>;
  logout: () => void;
  setAccountType: (accountType: AccountType) => Promise<void>;
  isFollowing: (id: string) => boolean;
  follow: (id: string) => Promise<void>;
  unfollow: (id: string) => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [followingIds, setFollowingIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!session) {
      setFollowingIds(new Set());
      return;
    }
    let active = true;
    api
      .getFollowing(session.user.id)
      .then((users) => {
        if (active) setFollowingIds(new Set(users.map((u) => u.id)));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [session]);

  const login = useCallback(async (name: string) => {
    const next = await api.login(name);
    saveSession(next);
    setSession(next);
  }, []);

  const logout = useCallback(() => {
    saveSession(null);
    setSession(null);
  }, []);

  const setAccountType = useCallback(
    async (accountType: AccountType) => {
      if (!session) return;
      const updated = await api.updateAccountType(session.user.id, accountType);
      const next: Session = { ...session, user: { ...session.user, accountType: updated.accountType } };
      saveSession(next);
      setSession(next);
    },
    [session],
  );

  const isFollowing = useCallback((id: string) => followingIds.has(id), [followingIds]);

  const follow = useCallback(
    async (id: string) => {
      if (!session) return;
      await api.follow(session.user.id, id);
      setFollowingIds((prev) => new Set(prev).add(id));
    },
    [session],
  );

  const unfollow = useCallback(
    async (id: string) => {
      if (!session) return;
      await api.unfollow(session.user.id, id);
      setFollowingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    },
    [session],
  );

  const value = useMemo<AuthValue>(
    () => ({ session, user: session?.user ?? null, login, logout, setAccountType, isFollowing, follow, unfollow }),
    [session, login, logout, setAccountType, isFollowing, follow, unfollow],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used within AuthProvider');
  return value;
}
