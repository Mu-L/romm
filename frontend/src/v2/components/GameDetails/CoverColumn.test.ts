import { shallowMount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DetailedRom } from "@/stores/roms";
import CoverColumn from "./CoverColumn.vue";

// The lightbox is auto-stubbed by shallowMount; match it by component name.
const CAROUSEL = { name: "RCarousel" };

const COVER_URL = "/assets/romm/resources/roms/1/cover/big.png";
const FALLBACK_URL = "https://provider.example/cover.png";

vi.mock("vue-i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

function rom(overrides: Partial<DetailedRom> = {}): DetailedRom {
  return {
    id: 1,
    is_identified: true,
    path_cover_large: COVER_URL,
    path_cover_small: null,
    url_cover: null,
    path_video: null,
    platform_slug: "snes",
    ss_metadata: null,
    gamelist_metadata: null,
    ...overrides,
  } as DetailedRom;
}

// Stands in for GameCover: renders the chrome slot (the default stub would
// swallow the zoom hint) and reports whichever src the test says is on screen.
function coverStub(renderedSrc: string | null) {
  return { setup: () => ({ renderedSrc }), template: "<div><slot /></div>" };
}

function mountCover(
  overrides: Partial<DetailedRom> = {},
  renderedSrc: string | null = COVER_URL,
) {
  return shallowMount(CoverColumn, {
    props: { rom: rom(overrides), alt: "Super Mario World" },
    global: { stubs: { GameCover: coverStub(renderedSrc) } },
  });
}

describe("CoverColumn zoom", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("opens the lightbox on the resolved cover", async () => {
    const wrapper = mountCover();
    const button = wrapper.get("button.r-v2-det-cover__zoom");

    expect(button.attributes("disabled")).toBeUndefined();
    expect(wrapper.find(".r-v2-det-cover__zoom-hint").exists()).toBe(true);
    expect(wrapper.findComponent(CAROUSEL).exists()).toBe(false);

    await button.trigger("click");

    const carousel = wrapper.findComponent(CAROUSEL);
    expect(carousel.exists()).toBe(true);
    expect(carousel.props("items")).toEqual([COVER_URL]);
  });

  it("follows the cover onto its fallback artwork", async () => {
    // The primary image failed, so the cover is painting `url_cover`.
    const wrapper = mountCover({ url_cover: FALLBACK_URL }, FALLBACK_URL);

    await wrapper.get("button.r-v2-det-cover__zoom").trigger("click");

    expect(wrapper.findComponent(CAROUSEL).props("items")).toEqual([
      FALLBACK_URL,
    ]);
  });

  it("stays inert when the rom has no cover to zoom into", () => {
    const wrapper = mountCover({ path_cover_large: null }, null);

    expect(
      wrapper.get("button.r-v2-det-cover__zoom").attributes("disabled"),
    ).toBeDefined();
    expect(wrapper.find(".r-v2-det-cover__zoom-hint").exists()).toBe(false);
    expect(wrapper.findComponent(CAROUSEL).exists()).toBe(false);
  });
});
