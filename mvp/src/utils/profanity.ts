import { RegExpMatcher, englishDataset, englishRecommendedTransformers } from 'obscenity';

// Mirror of the backend guard (better-profanity): the player name lands on the public booth TV /
// leaderboard, so block profanity (incl. leetspeak like "sh1t"/"f@ck") while leaving real names
// such as "Scunthorpe"/"Cockburn" alone. The backend 422 is authoritative; this is just instant
// in-form feedback so the player fixes it before submitting.
const matcher = new RegExpMatcher({
  ...englishDataset.build(),
  ...englishRecommendedTransformers,
});

export function isProfane(text: string): boolean {
  return text.trim().length > 0 && matcher.hasMatch(text);
}
