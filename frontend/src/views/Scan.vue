<script setup lang="ts">
import RomListItem from "@/components/common/Game/ListItem.vue";
import PlatformIcon from "@/components/common/Platform/Icon.vue";
import MissingFromFSIcon from "@/components/common/MissingFromFSIcon.vue";
import socket from "@/services/socket";
import storeHeartbeat from "@/stores/heartbeat";
import storePlatforms, { type Platform } from "@/stores/platforms";
import storeScanning from "@/stores/scanning";
import { ROUTES } from "@/plugins/router";
import { storeToRefs } from "pinia";
import { computed, ref, watch } from "vue";
import { useDisplay } from "vuetify";
import { useI18n } from "vue-i18n";

// Props
const { t } = useI18n();
const { xs, smAndDown } = useDisplay();
const scanningStore = storeScanning();
const { scanning, scanningPlatforms, scanStats } = storeToRefs(scanningStore);
const platforms = storePlatforms();
const heartbeat = storeHeartbeat();
const platformsToScan = ref<Platform[]>([]);
const panels = ref<number[]>([]);
// Use store getters
const metadataOptions = computed(() => heartbeat.getAllMetadataOptions());
const metadataSources = ref([...heartbeat.getEnabledMetadataOptions()]);

watch(metadataOptions, (newOptions) => {
  // Remove any sources that are now disabled
  metadataSources.value = metadataSources.value.filter((s) =>
    newOptions.some((opt) => opt.value === s.value && !opt.disabled),
  );
});

// Adding each new scanned platform to panelIndex to be open by default
watch(
  scanningPlatforms,
  () => {
    panels.value = scanningPlatforms.value
      .map((p, index) => (p.roms.length > 0 ? index : -1))
      .filter((index) => index !== -1);
  },
  { deep: true },
);

const scanOptions = [
  {
    title: t("scan.new-platforms"),
    subtitle: t("scan.new-platforms-desc"),
    value: "new_platforms",
  },
  {
    title: t("scan.quick-scan"),
    subtitle: t("scan.quick-scan-desc"),
    value: "quick",
  },
  {
    title: t("scan.unidentified-games"),
    subtitle: t("scan.unidentified-games-desc"),
    value: "unidentified",
  },
  {
    title: t("scan.partial-metadata"),
    subtitle: t("scan.partial-metadata-desc"),
    value: "partial",
  },
  {
    title: t("scan.hashes"),
    subtitle: t("scan.hashes-desc"),
    value: "hashes",
  },
  {
    title: t("scan.complete-rescan"),
    subtitle: t("scan.complete-rescan-desc"),
    value: "complete",
  },
];
const scanType = ref("quick");

async function scan() {
  scanningStore.set(true);
  scanningPlatforms.value = [];

  if (!socket.connected) socket.connect();

  socket.emit("scan", {
    platforms: platformsToScan.value.map((p) => p.id),
    type: scanType.value,
    apis: metadataSources.value.map((s) => s.value),
  });
}

socket.on("scan:done", (stats) => {
  scanStats.value = stats;
});

// TODO: fix abort scan
async function stopScan() {
  socket.emit("scan:stop");
}
</script>

<template>
  <v-row class="align-center pt-4 px-4" no-gutters>
    <!-- Platform selector -->
    <v-col cols="12" md="3" lg="4" class="px-1">
      <!-- TODO: add 'ALL' default option -->
      <v-select
        v-model="platformsToScan"
        :items="platforms.allPlatforms"
        :menu-props="{ maxHeight: 650 }"
        :label="t('common.platforms')"
        item-title="name"
        prepend-inner-icon="mdi-controller"
        variant="outlined"
        density="comfortable"
        multiple
        return-object
        clearable
        hide-details
        chips
      >
        <template #item="{ props, item }">
          <v-list-item
            v-bind="props"
            class="py-4"
            :title="item.raw.name ?? ''"
            :subtitle="item.raw.fs_slug"
          >
            <template #prepend>
              <platform-icon
                :key="item.raw.slug"
                :size="35"
                :slug="item.raw.slug"
                :name="item.raw.name"
                :fs-slug="item.raw.fs_slug"
              />
            </template>
            <template #append>
              <missing-from-f-s-icon
                v-if="item.raw.missing_from_fs"
                text="Missing platform from filesystem"
                chip
                chip-label
                chipDensity="compact"
                class="ml-2"
              />
              <v-chip class="ml-2" size="x-small" label>
                {{ item.raw.rom_count }}
              </v-chip>
            </template>
          </v-list-item>
        </template>
        <template #chip="{ item }">
          <v-chip>
            <platform-icon
              :key="item.raw.slug"
              :slug="item.raw.slug"
              :name="item.raw.name"
              :fs-slug="item.raw.fs_slug"
              :size="20"
              class="mr-2"
            />
            {{ item.raw.name }}
          </v-chip>
        </template>
      </v-select>
    </v-col>

    <!-- Source options -->
    <v-col cols="12" md="5" lg="6" class="px-1" :class="{ 'mt-3': smAndDown }">
      <v-select
        v-model="metadataSources"
        :items="metadataOptions"
        :label="t('scan.metadata-sources')"
        item-title="name"
        prepend-inner-icon="mdi-database-search"
        variant="outlined"
        density="comfortable"
        multiple
        return-object
        clearable
        hide-details
        chips
      >
        <template #item="{ props, item }">
          <v-list-item
            v-bind="props"
            :title="item.raw.name"
            :subtitle="item.raw.disabled"
            :disabled="Boolean(item.raw.disabled)"
          >
            <template #prepend>
              <v-avatar size="25" rounded="1">
                <v-img :src="item.raw.logo_path" />
              </v-avatar>
            </template>
          </v-list-item>
        </template>
        <template #chip="{ item }">
          <v-chip>
            <v-avatar class="mr-2" size="15" rounded="1">
              <v-img :src="item.raw.logo_path" />
            </v-avatar>
            {{ item.raw.name }}
          </v-chip>
        </template>
      </v-select>
    </v-col>

    <!-- Scan options -->
    <v-col cols="12" md="2" class="px-1" :class="{ 'mt-3': smAndDown }">
      <v-select
        v-model="scanType"
        :items="scanOptions"
        :label="t('scan.scan-options')"
        prepend-inner-icon="mdi-magnify-scan"
        hide-details
        density="comfortable"
        variant="outlined"
      >
        <template #item="{ props, item }">
          <v-list-item v-bind="props" :subtitle="item.raw.subtitle" />
        </template>
      </v-select>
    </v-col>
  </v-row>

  <!-- Scan buttons -->
  <v-row
    class="px-4 mt-3 align-center"
    :class="{ 'justify-center': smAndDown }"
    no-gutters
  >
    <v-btn
      :disabled="scanning"
      :loading="scanning"
      rounded="4"
      height="40"
      @click="scan"
    >
      <template #prepend>
        <v-icon :color="scanning ? '' : 'primary'">mdi-magnify-scan</v-icon>
      </template>
      {{ t("scan.scan") }}
      <template #loader>
        <v-progress-circular
          color="primary"
          :width="2"
          :size="20"
          indeterminate
        />
      </template>
    </v-btn>
    <v-btn
      :disabled="!scanning"
      class="ml-2"
      rounded="4"
      height="40"
      @click="stopScan"
    >
      <template #prepend>
        <v-icon :color="scanning ? 'red' : ''">mdi-alert-octagon</v-icon>
      </template>
      {{ t("scan.abort") }}
    </v-btn>
    <v-btn
      prepend-icon="mdi-table-cog"
      rounded="4"
      height="40"
      class="ml-2"
      :to="{ name: ROUTES.LIBRARY_MANAGEMENT }"
    >
      {{ t("scan.manage-library") }}
    </v-btn>
  </v-row>

  <v-row
    v-if="metadataSources.length == 0"
    no-gutters
    class="mt-3 justify-center"
  >
    <v-list-item class="text-caption text-yellow py-0">
      <v-icon>mdi-alert</v-icon
      ><span class="ml-2">{{ t("scan.select-one-source") }}</span>
    </v-list-item>
  </v-row>

  <v-divider
    class="border-opacity-100 mt-3"
    :class="{ 'mx-4': !smAndDown }"
    color="primary"
  />

  <!-- Scan log -->
  <v-row no-gutters>
    <v-col>
      <v-card
        elevation="0"
        class="bg-surface mx-auto mt-2 mb-14"
        max-width="800"
      >
        <v-card-text class="pa-0">
          <v-expansion-panels
            v-model="panels"
            multiple
            flat
            variant="accordion"
          >
            <v-expansion-panel
              v-for="platform in scanningPlatforms"
              :key="platform.id"
            >
              <v-expansion-panel-title static>
                <v-list-item class="pa-0">
                  <template #prepend>
                    <v-avatar rounded="0" size="40">
                      <platform-icon
                        :key="platform.slug"
                        :slug="platform.slug"
                        :name="platform.name"
                      />
                    </v-avatar>
                  </template>
                  {{ platform.name }}
                  <template #append>
                    <v-chip class="ml-3" color="primary" size="x-small" label>{{
                      platform.roms.length
                    }}</v-chip>
                  </template>
                </v-list-item>
              </v-expansion-panel-title>
              <v-expansion-panel-text class="bg-toplayer">
                <rom-list-item
                  v-for="rom in platform.roms"
                  class="pa-4"
                  :rom="rom"
                  with-link
                  with-filename
                >
                  <template #append>
                    <v-chip
                      v-if="rom.is_unidentified"
                      color="red"
                      size="x-small"
                      label
                    >
                      Not identified
                      <v-icon class="ml-1">mdi-close</v-icon>
                    </v-chip>
                    <v-chip
                      v-if="rom.hasheous_id"
                      title="Verified with Hasheous"
                      class="text-white pa-0 mr-1"
                      size="small"
                    >
                      <v-avatar class="bg-romm-green" size="26" rounded="0">
                        <v-icon>mdi-check-decagram-outline</v-icon>
                      </v-avatar>
                    </v-chip>
                    <v-chip
                      v-if="rom.igdb_id"
                      class="pa-0 mr-1"
                      size="small"
                      title="IGDB match"
                    >
                      <v-avatar size="26" rounded>
                        <v-img src="/assets/scrappers/igdb.png" />
                      </v-avatar>
                    </v-chip>
                    <v-chip
                      v-if="rom.ss_id"
                      class="pa-0 mr-1"
                      size="small"
                      title="ScreenScraper match"
                    >
                      <v-avatar size="26" rounded>
                        <v-img src="/assets/scrappers/ss.png" />
                      </v-avatar>
                    </v-chip>
                    <v-chip
                      v-if="rom.moby_id"
                      class="pa-0 mr-1"
                      size="small"
                      title="MobyGames match"
                    >
                      <v-avatar size="26" rounded>
                        <v-img src="/assets/scrappers/moby.png" />
                      </v-avatar>
                    </v-chip>
                    <v-chip
                      v-if="rom.launchbox_id"
                      class="pa-0 mr-1"
                      size="small"
                      title="LaunchBox match"
                    >
                      <v-avatar size="26" style="background: #185a7c">
                        <v-img src="/assets/scrappers/launchbox.png" />
                      </v-avatar>
                    </v-chip>
                    <v-chip
                      v-if="rom.ra_id"
                      class="pa-0 mr-1"
                      size="small"
                      title="RetroAchievements match"
                    >
                      <v-avatar size="26" rounded>
                        <v-img src="/assets/scrappers/ra.png" />
                      </v-avatar>
                    </v-chip>
                    <v-chip
                      v-if="rom.hasheous_id"
                      class="pa-1 mr-1 bg-surface"
                      size="small"
                      title="Hasheous match"
                    >
                      <v-avatar size="18" rounded>
                        <v-img src="/assets/scrappers/hasheous.png" />
                      </v-avatar>
                    </v-chip>
                  </template>
                </rom-list-item>
                <v-list-item
                  v-if="platform.roms.length == 0"
                  class="text-center my-2"
                >
                  {{ t("scan.no-new-roms") }}
                </v-list-item>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <!-- Scan stats -->
  <div
    v-if="scanningPlatforms.length > 0"
    class="text-caption position-fixed d-flex w-100 m-1 justify-center"
    style="bottom: 0.5rem"
  >
    <v-chip variant="outlined" color="toplayer" class="px-2 py-5 bg-background">
      <v-chip color="primary" text-color="white" size="small" class="mr-1 my-1">
        <v-icon left>mdi-controller</v-icon>
        <span v-if="xs" class="ml-2">{{
          t("scan.platforms-scanned-n", scanningPlatforms.length)
        }}</span>
        <span class="ml-2" v-else>{{
          t("scan.platforms-scanned-with-details", {
            n_platforms: scanningPlatforms.length,
            n_added_platforms: scanStats.added_platforms,
            n_identified_platforms: scanStats.metadata_platforms,
          })
        }}</span>
      </v-chip>
      <v-chip
        v-if="scanningPlatforms.length > 0"
        color="primary"
        size="small"
        text-color="white"
        class="ml-1 my-1"
      >
        <v-icon left> mdi-disc </v-icon>
        <span v-if="xs" class="ml-2">{{
          t("scan.roms-scanned-n", scanStats.scanned_roms)
        }}</span>
        <span class="ml-2" v-else>{{
          t("scan.roms-scanned-with-details", {
            n_roms: scanStats.scanned_roms,
            n_added_roms: scanStats.added_roms,
            n_identified_roms: scanStats.metadata_roms,
          })
        }}</span>
      </v-chip>
    </v-chip>
  </div>
</template>
<style lang="css">
.v-expansion-panel-text__wrapper {
  padding: 0px;
}
</style>
