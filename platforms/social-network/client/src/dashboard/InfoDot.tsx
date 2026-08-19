/**
 * A small "ⓘ" affordance that reveals a plain-English explanation on hover/focus.
 * Keyboard- and screen-reader-accessible. No native `title` — the styled popup is the only
 * tooltip, so the browser's default tooltip never doubles up on it.
 */
export function InfoDot({ text }: { text: string }) {
  return (
    <span className="info" tabIndex={0} role="note" aria-label={text}>
      i
      <span className="info-pop" aria-hidden="true">
        {text}
      </span>
    </span>
  );
}
