import type { Facet, SimilarityReasonSchema } from "@/__generated__";

/**
 * Maps a recommendation reason onto an icon and a display label.
 *
 * Facets whose value is already a proper noun (a franchise, a company)
 * display that value directly, since "Metroid" explains the match better
 * than "Same franchise" does. Facets with no meaningful value of their own
 * fall back to a translated phrase.
 *
 * Both maps are keyed by the generated `Facet` union, so adding a facet to
 * the backend enum fails the build here until it is given an icon.
 */

const FACET_ICONS: Record<Facet, string> = {
  collection: "mdi-bookmark-multiple-outline",
  franchise: "mdi-star-outline",
  developer: "mdi-domain",
  publisher: "mdi-domain",
  company: "mdi-domain",
  genre: "mdi-shape-outline",
  theme: "mdi-palette-outline",
  perspective: "mdi-camera-outline",
  keyword: "mdi-tag-multiple-outline",
  game_mode: "mdi-account-group-outline",
  platform: "mdi-controller-classic-outline",
  decade: "mdi-calendar-outline",
  igdb: "mdi-link-variant",
  top_rated: "mdi-trophy-outline",
};

/** Facets rendered as a translated phrase rather than their raw value. */
const TRANSLATED_FACETS: Partial<Record<Facet, string>> = {
  igdb: "recommendations.reason-igdb",
  top_rated: "recommendations.reason-top-rated",
};

export function reasonIcon(reason: SimilarityReasonSchema): string {
  return FACET_ICONS[reason.facet];
}

export function reasonLabel(
  reason: SimilarityReasonSchema,
  t: (key: string) => string,
): string {
  const translationKey = TRANSLATED_FACETS[reason.facet];
  if (translationKey) {
    return t(translationKey);
  }

  // Decades arrive as the starting year ("1990") and read better with the
  // plural suffix the rest of the UI uses.
  if (reason.facet === "decade") {
    return `${reason.value}s`;
  }

  return reason.value;
}
