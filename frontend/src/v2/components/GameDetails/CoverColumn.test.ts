import { shallowMount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DetailedRom } from "@/stores/roms";
import CoverColumn from "./CoverColumn.vue";

// The lightbox is auto-stubbed by shallowMount; match it by component name.
const CAROUSEL = { name: "RCarousel" };

vi.mock("vue-i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

function rom(overrides: Partial<DetailedRom> = {}): DetailedRom {
  return {
    id: 1,
    is_identified: true,
    path_cover_large: "/assets/romm/resources/roms/1/cover/big.png",
    path_cover_small: null,
    url_cover: null,
    path_video: null,
    platform_slug: "snes",
    ss_metadata: null,
    gamelist_metadata: null,
    ...overrides,
  } as DetailedRom;
}

function mountCover(overrides: Partial<DetailedRom> = {}) {
  return shallowMount(CoverColumn, {
    props: { rom: rom(overrides), alt: "Super Mario World" },
    // The zoom hint lives in GameCover's chrome slot, which the default
    // stub would swallow.
    global: { stubs: { GameCover: { template: "<div><slot /></div>" } } },
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
    expect(carousel.props("items")).toEqual([
      "/assets/romm/resources/roms/1/cover/big.png",
    ]);
  });

  it("stays inert when the rom has no cover to zoom into", async () => {
    const wrapper = mountCover({ path_cover_large: null });
    const button = wrapper.get("button.r-v2-det-cover__zoom");

    expect(button.attributes("disabled")).toBeDefined();
    expect(wrapper.find(".r-v2-det-cover__zoom-hint").exists()).toBe(false);

    await button.trigger("click");

    expect(wrapper.findComponent(CAROUSEL).exists()).toBe(false);
  });
});
