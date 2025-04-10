import type {
  MessageResponse,
  SearchRomSchema,
  RomUserSchema,
  RomSchema,
} from "@/__generated__";
import api from "@/services/api/index";
import socket from "@/services/socket";
import storeUpload from "@/stores/upload";
import type { DetailedRom, SimpleRom } from "@/stores/roms";
import { getDownloadPath } from "@/utils";
import type { AxiosProgressEvent } from "axios";
import storeHeartbeat from "@/stores/heartbeat";

export const romApi = api;

async function uploadRoms({
  platformId,
  filesToUpload,
}: {
  platformId: number;
  filesToUpload: File[];
}): Promise<PromiseSettledResult<RomSchema>[]> {
  const heartbeat = storeHeartbeat();

  if (!socket.connected) socket.connect();
  const uploadStore = storeUpload();

  const promises = filesToUpload.map((file) => {
    const formData = new FormData();
    formData.append(file.name, file);

    uploadStore.start(file.name);
    return new Promise<RomSchema>((resolve, reject) => {
      api
        .post("/roms", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
            "X-Upload-Platform": platformId.toString(),
            "X-Upload-Filename": file.name,
          },
          timeout: heartbeat.value.FRONTEND.UPLOAD_TIMEOUT * 1000,
          params: {},
          onUploadProgress: (progressEvent: AxiosProgressEvent) => {
            uploadStore.update(file.name, progressEvent);
          },
        })
        .then(({ data }) => {
          resolve(data);
        })
        .catch((error) => {
          uploadStore.fail(file.name, error.response?.data?.detail);
          reject(error);
        });
    });
  });

  return Promise.allSettled(promises);
}

async function getRoms({
  platformId = null,
  collectionId = null,
  virtualCollectionId = null,
  searchTerm = null,
  orderBy = "name",
  orderDir = "asc",
}: {
  platformId?: number | null;
  collectionId?: number | null;
  virtualCollectionId?: string | null;
  searchTerm?: string | null;
  orderBy?: string | null;
  orderDir?: string | null;
}): Promise<{ data: SimpleRom[] }> {
  return api.get(`/roms`, {
    params: {
      platform_id: platformId,
      collection_id: collectionId,
      virtual_collection_id: virtualCollectionId,
      search_term: searchTerm,
      order_by: orderBy,
      order_dir: orderDir,
      limit: 2500,
    },
  });
}

async function getRecentRoms(): Promise<{ data: SimpleRom[] }> {
  return api.get("/roms", {
    params: { order_by: "id", order_dir: "desc", limit: 15 },
  });
}

async function getRecentPlayedRoms(): Promise<{ data: SimpleRom[] }> {
  return api.get("/roms", {
    params: { order_by: "last_played", order_dir: "desc", limit: 15 },
  });
}

async function getRom({
  romId,
}: {
  romId: number;
}): Promise<{ data: DetailedRom }> {
  return api.get(`/roms/${romId}`);
}

async function searchRom({
  romId,
  searchTerm,
  searchBy,
}: {
  romId: number;
  searchTerm: string;
  searchBy: string;
}): Promise<{ data: SearchRomSchema[] }> {
  return api.get("/search/roms", {
    params: {
      rom_id: romId,
      search_term: searchTerm,
      search_by: searchBy,
    },
  });
}

// Used only for multi-file downloads
async function downloadRom({
  rom,
  fileIDs = [],
}: {
  rom: SimpleRom;
  fileIDs?: number[];
}) {
  const a = document.createElement("a");
  a.href = getDownloadPath({ rom, fileIDs });

  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export type UpdateRom = SimpleRom & {
  artwork?: File;
};

async function updateRom({
  rom,
  renameAsSource = false,
  removeCover = false,
  unmatch = false,
}: {
  rom: UpdateRom;
  renameAsSource?: boolean;
  removeCover?: boolean;
  unmatch?: boolean;
}): Promise<{ data: DetailedRom }> {
  const formData = new FormData();
  if (rom.igdb_id) formData.append("igdb_id", rom.igdb_id.toString());
  if (rom.moby_id) formData.append("moby_id", rom.moby_id.toString());
  if (rom.ss_id) formData.append("ss_id", rom.ss_id.toString());
  formData.append("name", rom.name || "");
  formData.append("fs_name", rom.fs_name);
  formData.append("summary", rom.summary || "");
  formData.append("url_cover", rom.url_cover || "");
  if (rom.artwork) formData.append("artwork", rom.artwork);

  return api.put(`/roms/${rom.id}`, formData, {
    params: {
      rename_as_source: renameAsSource,
      remove_cover: removeCover,
      unmatch_metadata: unmatch,
    },
  });
}

async function uploadManuals({
  romId,
  filesToUpload,
}: {
  romId: number;
  filesToUpload: File[];
}): Promise<PromiseSettledResult<unknown>[]> {
  const heartbeat = storeHeartbeat();
  const uploadStore = storeUpload();

  console.log(filesToUpload);
  const promises = filesToUpload.map((file) => {
    const formData = new FormData();
    formData.append(file.name, file);

    uploadStore.start(file.name);
    return new Promise((resolve, reject) => {
      api
        .post(`/roms/${romId}/manuals`, formData, {
          headers: {
            "Content-Type": "multipart/form-data",
            "X-Upload-Filename": file.name,
          },
          timeout: heartbeat.value.FRONTEND.UPLOAD_TIMEOUT * 1000,
          params: {},
          onUploadProgress: (progressEvent: AxiosProgressEvent) => {
            uploadStore.update(file.name, progressEvent);
          },
        })
        .then(resolve)
        .catch((error) => {
          uploadStore.fail(file.name, error.response?.data?.detail);
          reject(error);
        });
    });
  });

  return Promise.allSettled(promises);
}

async function updateUserRomProps({
  romId,
  data,
  updateLastPlayed = false,
  removeLastPlayed = false,
}: {
  romId: number;
  data: Partial<RomUserSchema>;
  updateLastPlayed?: boolean;
  removeLastPlayed?: boolean;
}): Promise<{ data: RomUserSchema }> {
  return api.put(`/roms/${romId}/props`, {
    data: data,
    update_last_played: updateLastPlayed,
    remove_last_played: removeLastPlayed,
  });
}

async function deleteRoms({
  roms,
  deleteFromFs = [],
}: {
  roms: SimpleRom[];
  deleteFromFs: number[];
}): Promise<{ data: MessageResponse }> {
  return api.post("/roms/delete", {
    roms: roms.map((r) => r.id),
    delete_from_fs: deleteFromFs,
  });
}

export default {
  uploadRoms,
  getRoms,
  getRecentRoms,
  getRecentPlayedRoms,
  getRom,
  downloadRom,
  searchRom,
  updateRom,
  uploadManuals,
  updateUserRomProps,
  deleteRoms,
};
