import { ComposeBox } from './ComposeBox';
import type { Post } from '../types';

export function ComposeModal({
  quoting,
  onClose,
  onPosted,
  onAuthRequired,
}: {
  quoting: Post | null;
  onClose: () => void;
  onPosted: (post: Post) => void;
  onAuthRequired: () => void;
}) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540, padding: 0, overflow: 'hidden' }}>
        <ComposeBox quoting={quoting} autoFocus onPosted={onPosted} onAuthRequired={onAuthRequired} />
      </div>
    </div>
  );
}
