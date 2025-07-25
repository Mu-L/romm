/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ScreenshotSchema } from './ScreenshotSchema';
export type SaveSchema = {
    id: number;
    rom_id: number;
    user_id: number;
    file_name: string;
    file_name_no_tags: string;
    file_name_no_ext: string;
    file_extension: string;
    file_path: string;
    file_size_bytes: number;
    full_path: string;
    download_path: string;
    missing_from_fs: boolean;
    created_at: string;
    updated_at: string;
    emulator: (string | null);
    screenshot: (ScreenshotSchema | null);
};

