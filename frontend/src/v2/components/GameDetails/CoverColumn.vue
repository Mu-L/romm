<script setup lang="ts">
// CoverColumn — fixed-width left column wrapping the shared GameCover. The
// cover honours the details-page boxart style (falling back to the
// gallery-wide one), animates on hover, paints the procedural placeholder
// when empty, and is the destination of the shared-element morph from the
// GameCard the user clicked through from — all of that lives in GameCover
// now; this just sizes the column.
//
// The flat cover is clickable: it opens the same fullscreen RCarousel
// lightbox the screenshot and artwork grids use, at the cover's full size.
//
// When the resolved boxart style is the 3D box AND the rom has the full set
// of flat scans (front + back + spine, from ScreenScraper), the hero
// upgrades to the interactive RBox3D the user can spin. Anything missing —
// a different style, an incomplete set, or a failed image — falls straight
// back to the flat GameCover.
import { RBox3D, RCarousel, RIcon } from "@v2/lib";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { DetailedRom } from "@/stores/roms";
import GameCover from "@/v2/components/shared/GameCover.vue";
import { useBoxFaces } from "@/v2/composables/useBoxFaces";
import { useBoxartStyle, useCoverArt } from "@/v2/composables/useCoverArt";

defineOptions({ inheritAttrs: false });

const props = defineProps<{
  rom: DetailedRom;
  alt: string;
}>();

const { t } = useI18n();
const detailsStyle = useBoxartStyle("details");
const faces = useBoxFaces(() => props.rom);
const box3dFailed = ref(false);

// Resolved faces, or null when the interactive box can't / shouldn't render.
// Returning the concrete object keeps the template free of non-null asserts.
const box3d = computed(() => {
  if (detailsStyle.value !== "box3d_path" || box3dFailed.value) return null;
  const f = faces.value;
  if (!f.complete || !f.front || !f.back || !f.spine) return null;
  return { front: f.front, back: f.back, spine: f.spine };
});

// Same resolution GameCover runs internally, so the lightbox shows exactly
// the artwork on screen. Null means the cover is a placeholder: nothing to
// zoom into, so the hero stays inert.
const art = useCoverArt(() => props.rom, { context: () => "details" });
const zoomSrc = computed(() => art.coverUrl.value ?? art.fallbackUrl.value);
const zoomOpen = ref(false);
</script>

<template>
  <div class="r-v2-det-cover">
    <RBox3D
      v-if="box3d"
      class="r-v2-det-cover__box3d"
      :front="box3d.front"
      :back="box3d.back"
      :spine="box3d.spine"
      :alt="t('rom.box3d-alt', { title: alt })"
      @error="box3dFailed = true"
    />
    <button
      v-else
      type="button"
      class="r-v2-det-cover__zoom"
      :disabled="!zoomSrc"
      :aria-label="t('rom.cover-open')"
      @click="zoomOpen = true"
    >
      <GameCover
        class="r-v2-det-cover__art"
        :rom="rom"
        :title="alt"
        :identified="rom.is_identified"
        :morph-id="rom.id"
        style-context="details"
        morph-static
        hover-motion
      >
        <span v-if="zoomSrc" class="r-v2-det-cover__zoom-hint">
          <RIcon icon="mdi-magnify-plus-outline" size="18" />
        </span>
      </GameCover>
    </button>

    <RCarousel
      v-if="zoomOpen && zoomSrc"
      :model-value="0"
      :items="[zoomSrc]"
      fullscreen
      :aria-label="t('rom.cover-art')"
      @close="zoomOpen = false"
    >
      <template #default="{ item }">
        <img :src="item" :alt="alt" />
      </template>
    </RCarousel>
  </div>
</template>

<style scoped>
.r-v2-det-cover {
  flex-shrink: 0;
  align-self: flex-start;
  /* No sticky needed: GameDetails fits the main viewport exactly and only
     the inner tab panel scrolls. */
  padding-top: 40px;
  width: var(--r-cover-w);
}
/* Larger radius than the gallery card (this is the hero cover). */
.r-v2-det-cover__art {
  --r-cover-radius: var(--r-radius-lg);
}

.r-v2-det-cover__zoom {
  display: block;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  border-radius: var(--r-radius-lg);
  cursor: pointer;
}
.r-v2-det-cover__zoom:disabled {
  cursor: default;
}

.r-v2-det-cover__zoom-hint {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: var(--r-color-overlay-scrim-strong);
  color: var(--r-color-overlay-fg);
  opacity: 0;
  transition: opacity var(--r-motion-fast) var(--r-motion-ease-out);
}
.r-v2-det-cover__zoom:hover .r-v2-det-cover__zoom-hint,
.r-v2-det-cover__zoom:focus-visible .r-v2-det-cover__zoom-hint {
  opacity: 1;
}
/* No hover on touch / gamepad — keep the affordance visible there. */
html[data-input="touch"] .r-v2-det-cover__zoom-hint,
html[data-input="pad"] .r-v2-det-cover__zoom-hint {
  opacity: 1;
}

/* Stacked layout (sm-and-down): the cover sits centred above the info
   column at a readable hero size instead of the old ~100px side rail. */
html[data-bp~="sm-and-down"] .r-v2-det-cover {
  width: clamp(160px, 50vw, 260px);
  align-self: center;
  padding-top: 0;
}
</style>
