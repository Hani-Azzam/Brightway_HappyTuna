import { useOutletContext } from 'react-router-dom';
import type { Post } from '../types';

export interface ShellContext {
  /** Open the login dialog (e.g. when a guest tries to act). */
  onAuthRequired: () => void;
  /** Open the composer pre-filled to quote the given post. */
  onQuote: (post: Post) => void;
}

export function useShell(): ShellContext {
  return useOutletContext<ShellContext>();
}
