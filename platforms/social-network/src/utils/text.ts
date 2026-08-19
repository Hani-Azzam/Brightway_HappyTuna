/**
 * Extracts unique, lowercased hashtags (without the leading '#') from post content.
 * Matches ASCII word characters and caps each tag at 50 characters.
 */
export function extractHashtags(content: string): string[] {
  const tags = new Set<string>();
  for (const match of content.matchAll(/#(\w{1,50})/g)) {
    tags.add(match[1]!.toLowerCase());
  }
  return [...tags];
}
