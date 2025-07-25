<script setup lang="ts">
import type { SearchCoverSchema } from "@/__generated__";
import RDialog from "@/components/common/RDialog.vue";
import sgdbApi from "@/services/api/sgdb";
import storeGalleryView from "@/stores/galleryView";
import storePlatforms from "@/stores/platforms";
import type { Events } from "@/types/emitter";
import type { Emitter } from "mitt";
import { inject, onBeforeUnmount, ref } from "vue";
import { useDisplay } from "vuetify";

// Props
const { lgAndUp } = useDisplay();
const show = ref(false);
const searching = ref(false);
const searchText = ref("");
const coverType = ref("all");
const covers = ref<SearchCoverSchema[]>([]);
const filteredCovers = ref<SearchCoverSchema[]>();
const galleryViewStore = storeGalleryView();
const panels = ref([0]);
const emitter = inject<Emitter<Events>>("emitter");
const coverAspectRatio = ref(
  parseFloat(galleryViewStore.defaultAspectRatioCover.toString()),
);
emitter?.on("showSearchCoverDialog", ({ term, aspectRatio = null }) => {
  searchText.value = term;
  show.value = true;
  // TODO: set default aspect ratio to 2/3
  if (aspectRatio) coverAspectRatio.value = aspectRatio;
  if (searchText.value) searchCovers();
});

// Functions
async function searchCovers() {
  covers.value = [];

  // Auto hide android keyboard
  const inputElement = document.getElementById("search-text-field");
  inputElement?.blur();

  if (!searching.value) {
    searching.value = true;
    await sgdbApi
      .searchCover({
        searchTerm: searchText.value,
      })
      .then((response) => {
        covers.value = response.data;
        filteredCovers.value = covers.value
          .map((game) => {
            return {
              ...game,
              resources:
                coverType.value === "all"
                  ? game.resources
                  : game.resources.filter(
                      (resource) => resource.type === coverType.value,
                    ),
            };
          })
          .filter((item) => item.resources.length > 0);
      })
      .catch((error) => {
        emitter?.emit("snackbarShow", {
          msg: error.response.data.detail,
          icon: "mdi-close-circle",
          color: "red",
        });
      })
      .finally(() => {
        searching.value = false;
      });
  }
}

async function selectCover(url_cover: string) {
  emitter?.emit("updateUrlCover", url_cover.replace("thumb", "grid"));
  closeDialog();
}

function filterCovers() {
  if (covers.value) {
    filteredCovers.value = covers.value
      .map((game) => {
        return {
          ...game,
          resources:
            coverType.value === "all"
              ? game.resources
              : game.resources.filter(
                  (resource) => resource.type === coverType.value,
                ),
        };
      })
      .filter((item) => item.resources.length > 0);
  }
}

function closeDialog() {
  show.value = false;
  covers.value = [];
  filteredCovers.value = [];
  searchText.value = "";
}

onBeforeUnmount(() => {
  emitter?.off("showSearchCoverDialog");
});
</script>

<template>
  <r-dialog
    @close="closeDialog"
    v-model="show"
    icon="mdi-image-search-outline"
    :loading-condition="searching"
    :empty-state-condition="filteredCovers?.length == 0"
    empty-state-type="game"
    scroll-content
    :width="lgAndUp ? '60vw' : '95vw'"
    :height="lgAndUp ? '90vh' : '775px'"
  >
    <template #toolbar>
      <v-row class="align-center" no-gutters>
        <v-col cols="8" sm="9">
          <v-text-field
            id="search-text-field"
            @keyup.enter="searchCovers"
            @click:clear="searchText = ''"
            class="bg-toplayer"
            v-model="searchText"
            :disabled="searching"
            label="Search"
            hide-details
            clearable
          />
        </v-col>
        <v-col cols="2" sm="2">
          <v-select
            :disabled="searching"
            v-model="coverType"
            hide-details
            label="Type"
            @update:model-value="filterCovers"
            :items="['all', 'static', 'animated']"
          />
        </v-col>
        <v-col>
          <v-btn
            type="submit"
            @click="searchCovers"
            class="bg-toplayer"
            variant="text"
            icon="mdi-search-web"
            block
            rounded="0"
            :disabled="searching"
          />
        </v-col>
      </v-row>
    </template>
    <template #content>
      <v-expansion-panels
        :model-value="panels"
        multiple
        flat
        variant="accordion"
      >
        <v-expansion-panel v-for="game in filteredCovers" :key="game.name">
          <v-expansion-panel-title class="bg-toplayer">
            <v-row no-gutters class="justify-center">
              <v-list-item class="pa-0">{{ game.name }}</v-list-item>
            </v-row>
          </v-expansion-panel-title>
          <v-expansion-panel-text class="py-1">
            <v-row no-gutters>
              <v-col
                class="pa-1"
                cols="4"
                sm="3"
                md="2"
                v-for="resource in game.resources"
              >
                <v-hover v-slot="{ isHovering, props: hoverProps }">
                  <!-- TODO: fix aspect ratio -->
                  <v-img
                    v-bind="hoverProps"
                    :class="{ 'on-hover': isHovering }"
                    class="transform-scale pointer"
                    @click="selectCover(resource.url)"
                    :aspect-ratio="coverAspectRatio"
                    :src="resource.thumb"
                    cover
                  >
                    <template #error>
                      <!-- TODO: fix aspect ratio -->
                      <v-img
                        :src="resource.url"
                        cover
                        :aspect-ratio="galleryViewStore.defaultAspectRatioCover"
                      ></v-img>
                    </template>
                    <template #placeholder>
                      <div
                        class="d-flex align-center justify-center fill-height"
                      >
                        <v-progress-circular
                          :width="2"
                          :size="40"
                          color="primary"
                          indeterminate
                        />
                      </div>
                    </template>
                  </v-img>
                </v-hover>
              </v-col>
            </v-row>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>
  </r-dialog>
</template>
<style lang="css">
.v-expansion-panel-text__wrapper {
  padding: 0px !important;
}
</style>
