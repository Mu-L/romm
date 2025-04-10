import type { PlatformSchema } from "@/__generated__";
import { uniqBy } from "lodash";
import { defineStore } from "pinia";

export type Platform = PlatformSchema;

export default defineStore("platforms", {
  state: () => ({
    allPlatforms: [] as Platform[],
    searchText: "" as string,
  }),

  getters: {
    totalGames: ({ allPlatforms: value }) =>
      value.reduce((count, p) => count + p.rom_count, 0),
    filledPlatforms: ({ allPlatforms: all }) =>
      all
        .filter((p) => p.rom_count > 0)
        .sort((a, b) => a.display_name.localeCompare(b.display_name)),
    filteredPlatforms: ({ allPlatforms: all, searchText }) =>
      all
        .filter(
          (p) =>
            p.rom_count > 0 &&
            p.display_name.toLowerCase().includes(searchText.toLowerCase()),
        )
        .sort((a, b) => a.display_name.localeCompare(b.display_name)),
  },
  actions: {
    _reorder() {
      this.allPlatforms = uniqBy(this.allPlatforms, "id").sort((a, b) => {
        return a.name.localeCompare(b.name);
      });
    },
    set(platforms: Platform[]) {
      this.allPlatforms = platforms;
      this._reorder();
    },
    add(platform: Platform) {
      this.allPlatforms.push(platform);
      this._reorder();
    },
    update(platform: Platform) {
      const index = this.allPlatforms.findIndex((p) => p.id === platform.id);
      this.allPlatforms[index] = platform;
      this._reorder();
    },
    has(id: number) {
      return this.allPlatforms.some((p) => p.id == id);
    },
    remove(platform: Platform) {
      this.allPlatforms = this.allPlatforms.filter((p) => {
        return p.slug !== platform.slug;
      });
    },
    get(platformId: number) {
      return this.allPlatforms.find((p) => p.id === platformId);
    },
    getAspectRatio(platformId: number): number {
      const platform = this.allPlatforms.find((p) => p.id === platformId);
      return platform && platform.aspect_ratio
        ? parseFloat(eval(platform.aspect_ratio as string))
        : 2 / 3;
    },
    reset() {
      this.allPlatforms = [] as Platform[];
      this.searchText = "";
    },
  },
});
