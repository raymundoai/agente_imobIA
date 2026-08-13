export type CompatibilityFilter = "all" | "perfect" | "high" | "lower";

export function compatibilityBucket(score: number): Exclude<CompatibilityFilter, "all"> {
  if (score === 100) return "perfect";
  if (score >= 80) return "high";
  return "lower";
}

export function matchesCompatibilityFilter(
  score: number,
  filter: CompatibilityFilter,
): boolean {
  return filter === "all" || compatibilityBucket(score) === filter;
}

export function compatibilityCounts(scores: number[]) {
  return scores.reduce(
    (counts, score) => ({ ...counts, [compatibilityBucket(score)]: counts[compatibilityBucket(score)] + 1 }),
    { perfect: 0, high: 0, lower: 0 },
  );
}
