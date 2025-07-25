import binascii
from base64 import b64encode
from datetime import datetime, timezone
from io import BytesIO
from stat import S_IFREG
from typing import Annotated, Any
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from anyio import Path, open_file
from config import (
    DEV_MODE,
    DISABLE_DOWNLOAD_ENDPOINT_AUTH,
    LIBRARY_BASE_PATH,
    str_to_bool,
)
from decorators.auth import protected_route
from endpoints.responses import MessageResponse
from endpoints.responses.rom import (
    DetailedRomSchema,
    RomFileSchema,
    RomUserSchema,
    SimpleRomSchema,
)
from exceptions.endpoint_exceptions import RomNotFoundInDatabaseException
from exceptions.fs_exceptions import RomAlreadyExistsException
from fastapi import (
    Body,
    File,
    Header,
    HTTPException,
)
from fastapi import Path as PathVar
from fastapi import (
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response
from fastapi_pagination.ext.sqlalchemy import paginate
from fastapi_pagination.limit_offset import LimitOffsetPage, LimitOffsetParams
from handler.auth.constants import Scope
from handler.database import db_platform_handler, db_rom_handler
from handler.database.base_handler import sync_session
from handler.filesystem import fs_resource_handler, fs_rom_handler
from handler.filesystem.base_handler import CoverSize
from handler.metadata import (
    meta_igdb_handler,
    meta_launchbox_handler,
    meta_moby_handler,
    meta_ss_handler,
)
from logger.formatter import BLUE
from logger.formatter import highlight as hl
from logger.logger import log
from models.rom import RomFile
from pydantic import BaseModel
from starlette.requests import ClientDisconnect
from starlette.responses import FileResponse
from streaming_form_data import StreamingFormDataParser
from streaming_form_data.targets import FileTarget, NullTarget
from utils.filesystem import sanitize_filename
from utils.hashing import crc32_to_hex
from utils.nginx import FileRedirectResponse, ZipContentLine, ZipResponse
from utils.router import APIRouter

router = APIRouter(
    prefix="/roms",
    tags=["roms"],
)


@protected_route(
    router.post,
    "",
    [Scope.ROMS_WRITE],
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_400_BAD_REQUEST: {}},
)
async def add_rom(
    request: Request,
    platform_id: Annotated[
        int,
        Header(description="Platform internal id.", ge=1, alias="x-upload-platform"),
    ],
    filename: Annotated[
        str,
        Header(
            description="The name of the file being uploaded.",
            alias="x-upload-filename",
        ),
    ],
) -> Response:
    """Upload a single rom."""

    if not platform_id or not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No platform ID or filename provided",
        )

    db_platform = db_platform_handler.get_platform(platform_id)
    if not db_platform:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform not found",
        )

    platform_fs_slug = db_platform.fs_slug
    roms_path = fs_rom_handler.get_roms_fs_structure(platform_fs_slug)
    log.info(
        f"Uploading file to {hl(db_platform.custom_name or db_platform.name, color=BLUE)}[{hl(platform_fs_slug)}]"
    )

    file_location = fs_rom_handler.validate_path(f"{roms_path}/{filename}")

    parser = StreamingFormDataParser(headers=request.headers)
    parser.register("x-upload-platform", NullTarget())
    parser.register(filename, FileTarget(str(file_location)))

    # Check if the file already exists
    if await fs_rom_handler.file_exists(f"{roms_path}/{filename}"):
        log.warning(f" - Skipping {hl(filename)} since the file already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File {filename} already exists",
        )

    # Create the directory if it doesn't exist
    await fs_rom_handler.make_directory(roms_path)

    def cleanup_partial_file():
        if file_location.exists():
            file_location.unlink()

    try:
        async for chunk in request.stream():
            parser.data_received(chunk)
    except ClientDisconnect:
        log.error("Client disconnected during upload")
        cleanup_partial_file()
    except Exception as exc:
        log.error("Error uploading files", exc_info=exc)
        cleanup_partial_file()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="There was an error uploading the file(s)",
        ) from exc

    return Response()


class CustomLimitOffsetParams(LimitOffsetParams):
    # Temporarily increase the limit until we can implement pagination on all apps
    limit: int = Query(50, ge=1, le=10_000, description="Page size limit")
    offset: int = Query(0, ge=0, description="Page offset")


class CustomLimitOffsetPage[T: BaseModel](LimitOffsetPage[T]):
    char_index: dict[str, int]
    __params_type__ = CustomLimitOffsetParams


@protected_route(router.get, "", [Scope.ROMS_READ])
def get_roms(
    request: Request,
    search_term: Annotated[
        str | None,
        Query(description="Search term to filter roms."),
    ] = None,
    platform_id: Annotated[
        int | None,
        Query(description="Platform internal id.", ge=1),
    ] = None,
    collection_id: Annotated[
        int | None,
        Query(description="Collection internal id.", ge=1),
    ] = None,
    virtual_collection_id: Annotated[
        str | None,
        Query(description="Virtual collection internal id."),
    ] = None,
    matched: Annotated[
        bool | None,
        Query(description="Whether the rom matched a metadata source."),
    ] = None,
    favourite: Annotated[
        bool | None,
        Query(description="Whether the rom is marked as favourite."),
    ] = None,
    duplicate: Annotated[
        bool | None,
        Query(description="Whether the rom is marked as duplicate."),
    ] = None,
    playable: Annotated[
        bool | None,
        Query(description="Whether the rom is playable from the browser."),
    ] = None,
    missing: Annotated[
        bool | None,
        Query(description="Whether the rom is missing from the filesystem."),
    ] = None,
    has_ra: Annotated[
        bool | None,
        Query(description="Whether the rom has RetroAchievements data."),
    ] = None,
    verified: Annotated[
        bool | None,
        Query(
            description="Whether the rom is verified by Hasheous from the filesystem."
        ),
    ] = None,
    group_by_meta_id: Annotated[
        bool,
        Query(
            description="Whether to group roms by metadata ID (IGDB / Moby / ScreenScraper / RetroAchievements / LaunchBox)."
        ),
    ] = False,
    selected_genre: Annotated[
        str | None,
        Query(description="Associated genre."),
    ] = None,
    selected_franchise: Annotated[
        str | None,
        Query(description="Associated franchise."),
    ] = None,
    selected_collection: Annotated[
        str | None,
        Query(description="Associated collection."),
    ] = None,
    selected_company: Annotated[
        str | None,
        Query(description="Associated company."),
    ] = None,
    selected_age_rating: Annotated[
        str | None,
        Query(description="Associated age rating."),
    ] = None,
    selected_status: Annotated[
        str | None,
        Query(description="Game status, set by the current user."),
    ] = None,
    selected_region: Annotated[
        str | None,
        Query(description="Associated region tag."),
    ] = None,
    selected_language: Annotated[
        str | None,
        Query(description="Associated language tag."),
    ] = None,
    order_by: Annotated[
        str,
        Query(description="Field to order results by."),
    ] = "name",
    order_dir: Annotated[
        str,
        Query(description="Order direction, either 'asc' or 'desc'."),
    ] = "asc",
) -> CustomLimitOffsetPage[SimpleRomSchema]:
    """Retrieve roms."""

    # Get the base roms query
    query = db_rom_handler.get_roms_query(
        user_id=request.user.id,
        order_by=order_by.lower(),
        order_dir=order_dir.lower(),
    )

    # Filter down the query
    query = db_rom_handler.filter_roms(
        query=query,
        user_id=request.user.id,
        platform_id=platform_id,
        collection_id=collection_id,
        virtual_collection_id=virtual_collection_id,
        search_term=search_term,
        matched=matched,
        favourite=favourite,
        duplicate=duplicate,
        playable=playable,
        has_ra=has_ra,
        missing=missing,
        verified=verified,
        selected_genre=selected_genre,
        selected_franchise=selected_franchise,
        selected_collection=selected_collection,
        selected_company=selected_company,
        selected_age_rating=selected_age_rating,
        selected_status=selected_status,
        selected_region=selected_region,
        selected_language=selected_language,
        group_by_meta_id=group_by_meta_id,
    )

    # Get the char index for the roms
    char_index = db_rom_handler.get_char_index(query=query)
    char_index_dict = {char: index for (char, index) in char_index}

    with sync_session.begin() as session:
        return paginate(
            session,
            query,
            transformer=lambda items: [
                SimpleRomSchema.from_orm_with_request(i, request) for i in items
            ],
            additional_data={"char_index": char_index_dict},
        )


@protected_route(
    router.get,
    "/{id}",
    [] if DISABLE_DOWNLOAD_ENDPOINT_AUTH else [Scope.ROMS_READ],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
def get_rom(
    request: Request,
    id: Annotated[int, PathVar(description="Rom internal id.", ge=1)],
) -> DetailedRomSchema:
    """Retrieve a rom by ID."""

    rom = db_rom_handler.get_rom(id)

    if not rom:
        raise RomNotFoundInDatabaseException(id)

    return DetailedRomSchema.from_orm_with_request(rom, request)


@protected_route(
    router.head,
    "/{id}/content/{file_name}",
    [] if DISABLE_DOWNLOAD_ENDPOINT_AUTH else [Scope.ROMS_READ],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def head_rom_content(
    request: Request,
    id: Annotated[int, PathVar(description="Rom internal id.", ge=1)],
    file_name: Annotated[str, PathVar(description="File name to download")],
    file_ids: Annotated[
        str | None,
        Query(
            description="Comma-separated list of file ids to download for multi-part roms."
        ),
    ] = None,
):
    """Retrieve head information for a rom file download."""

    rom = db_rom_handler.get_rom(id)

    if not rom:
        raise RomNotFoundInDatabaseException(id)

    files = rom.files
    if file_ids:
        file_id_values = {int(f.strip()) for f in file_ids.split(",") if f.strip()}
        files = [f for f in rom.files if f.id in file_id_values]
    files.sort(key=lambda x: x.file_name)

    # Serve the file directly in development mode for emulatorjs
    if DEV_MODE:
        if len(files) == 1:
            file = files[0]
            rom_path = f"{LIBRARY_BASE_PATH}/{file.full_path}"
            return FileResponse(
                path=rom_path,
                filename=file.file_name,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.file_name)}; filename=\"{quote(file.file_name)}\"",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(file.file_size_bytes),
                },
            )

        return Response(
            headers={
                "Content-Type": "application/zip",
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}.zip; filename=\"{quote(file_name)}.zip\"",
            },
        )

    # Otherwise proxy through nginx
    if len(files) == 1:
        return FileRedirectResponse(
            download_path=Path(f"/library/{files[0].full_path}"),
        )

    return Response(
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}.zip; filename=\"{quote(file_name)}.zip\"",
        },
    )


@protected_route(
    router.get,
    "/{id}/content/{file_name}",
    [] if DISABLE_DOWNLOAD_ENDPOINT_AUTH else [Scope.ROMS_READ],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def get_rom_content(
    request: Request,
    id: Annotated[int, PathVar(description="Rom internal id.", ge=1)],
    file_name: Annotated[str, PathVar(description="Zip file output name")],
    file_ids: Annotated[
        str | None,
        Query(
            description="Comma-separated list of file ids to download for multi-part roms."
        ),
    ] = None,
):
    """Download a rom.

    This endpoint serves the content of the requested rom, as:
    - A single file for single file roms.
    - A zipped file for multi-part roms, including a .m3u file if applicable.
    """

    current_username = (
        request.user.username if request.user.is_authenticated else "unknown"
    )
    rom = db_rom_handler.get_rom(id)

    if not rom:
        raise RomNotFoundInDatabaseException(id)

    # https://muos.dev/help/addcontent#what-about-multi-disc-content
    hidden_folder = str_to_bool(request.query_params.get("hidden_folder", ""))

    files = rom.files
    if file_ids:
        file_id_values = {int(f.strip()) for f in file_ids.split(",") if f.strip()}
        files = [f for f in rom.files if f.id in file_id_values]
    files.sort(key=lambda x: x.file_name)

    log.info(
        f"User {hl(current_username, color=BLUE)} is downloading {hl(rom.fs_name)}"
    )

    # Serve the file directly in development mode for emulatorjs
    if DEV_MODE:
        if len(files) == 1:
            file = files[0]
            rom_path = f"{LIBRARY_BASE_PATH}/{file.full_path}"
            return FileResponse(
                path=rom_path,
                filename=file.file_name,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.file_name)}; filename=\"{quote(file.file_name)}\"",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(file.file_size_bytes),
                },
            )

        async def build_zip_in_memory() -> bytes:
            # Initialize in-memory buffer
            zip_buffer = BytesIO()
            now = datetime.now()

            with ZipFile(zip_buffer, "w") as zip_file:
                # Add content files
                for file in files:
                    file_path = f"{LIBRARY_BASE_PATH}/{file.full_path}"
                    try:
                        # Read entire file into memory
                        async with await open_file(file_path, "rb") as f:
                            content = await f.read()

                        # Create ZIP info with compression
                        zip_info = ZipInfo(
                            filename=file.file_name_for_download(rom, hidden_folder),
                            date_time=now.timetuple()[:6],
                        )
                        zip_info.external_attr = S_IFREG | 0o600
                        zip_info.compress_type = (
                            ZIP_DEFLATED if file.file_size_bytes > 0 else ZIP_STORED
                        )

                        # Write file to ZIP
                        zip_file.writestr(zip_info, content)

                    except FileNotFoundError:
                        log.error(f"File {hl(file_path)} not found!")
                        raise

                # Add M3U file if not already present
                if not rom.has_m3u_file():
                    m3u_encoded_content = "\n".join(
                        [f.file_name_for_download(rom, hidden_folder) for f in files]
                    ).encode()
                    m3u_filename = f"{rom.fs_name}.m3u"
                    m3u_info = ZipInfo(
                        filename=m3u_filename, date_time=now.timetuple()[:6]
                    )
                    m3u_info.external_attr = S_IFREG | 0o600
                    m3u_info.compress_type = ZIP_STORED
                    zip_file.writestr(m3u_info, m3u_encoded_content)

            # Get the completed ZIP file bytes
            zip_buffer.seek(0)
            return zip_buffer.getvalue()

        zip_data = await build_zip_in_memory()

        # Streams the zip file to the client
        return Response(
            content=zip_data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}.zip; filename=\"{quote(file_name)}.zip\"",
            },
        )

    # Otherwise proxy through nginx
    if len(files) == 1:
        return FileRedirectResponse(
            download_path=Path(f"/library/{files[0].full_path}"),
        )

    async def create_zip_content(f: RomFile, base_path: str = LIBRARY_BASE_PATH):
        file_size = await fs_rom_handler.get_file_size(f.full_path)
        return ZipContentLine(
            crc32=f.crc_hash,
            size_bytes=file_size,
            encoded_location=quote(f"{base_path}/{f.full_path}"),
            filename=f.file_name_for_download(rom, hidden_folder),
        )

    content_lines = [await create_zip_content(f, "/library-zip") for f in files]

    if not rom.has_m3u_file():
        m3u_encoded_content = "\n".join(
            [f.file_name_for_download(rom, hidden_folder) for f in files]
        ).encode()
        m3u_base64_content = b64encode(m3u_encoded_content).decode()
        m3u_line = ZipContentLine(
            crc32=crc32_to_hex(binascii.crc32(m3u_encoded_content)),
            size_bytes=len(m3u_encoded_content),
            encoded_location=f"/decode?value={m3u_base64_content}",
            filename=f"{file_name}.m3u",
        )
        content_lines.append(m3u_line)

    return ZipResponse(
        content_lines=content_lines,
        filename=f"{quote(file_name)}.zip",
    )


@protected_route(
    router.put,
    "/{id}",
    [Scope.ROMS_WRITE],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def update_rom(
    request: Request,
    id: Annotated[int, PathVar(description="Rom internal id.", ge=1)],
    artwork: Annotated[
        UploadFile | None,
        File(description="Custom artwork to set as cover."),
    ] = None,
    remove_cover: Annotated[
        bool,
        Query(description="Whether to remove the cover image for this rom."),
    ] = False,
    unmatch_metadata: Annotated[
        bool,
        Query(description="Whether to remove the metadata matches for this game."),
    ] = False,
) -> DetailedRomSchema:
    """Update a rom."""
    data = await request.form()

    rom = db_rom_handler.get_rom(id)

    if not rom:
        raise RomNotFoundInDatabaseException(id)

    if unmatch_metadata:
        db_rom_handler.update_rom(
            id,
            {
                "igdb_id": None,
                "sgdb_id": None,
                "moby_id": None,
                "ss_id": None,
                "ra_id": None,
                "launchbox_id": None,
                "name": rom.fs_name,
                "summary": "",
                "url_screenshots": [],
                "path_screenshots": [],
                "path_cover_s": "",
                "path_cover_l": "",
                "url_cover": "",
                "url_manual": "",
                "slug": "",
                "igdb_metadata": {},
                "moby_metadata": {},
                "ss_metadata": {},
                "ra_metadata": {},
                "launchbox_metadata": {},
                "revision": "",
            },
        )

        rom = db_rom_handler.get_rom(id)
        if not rom:
            raise RomNotFoundInDatabaseException(id)

        return DetailedRomSchema.from_orm_with_request(rom, request)

    cleaned_data: dict[str, Any] = {
        "igdb_id": data.get("igdb_id", rom.igdb_id),
        "moby_id": data.get("moby_id", rom.moby_id),
        "ss_id": data.get("ss_id", rom.ss_id),
        "launchbox_id": data.get("launchbox_id", rom.launchbox_id),
    }

    if (
        cleaned_data.get("moby_id", "")
        and int(cleaned_data.get("moby_id", "")) != rom.moby_id
    ):
        moby_rom = await meta_moby_handler.get_rom_by_id(
            int(cleaned_data.get("moby_id", ""))
        )
        cleaned_data.update(moby_rom)
        path_screenshots = await fs_resource_handler.get_rom_screenshots(
            rom=rom,
            url_screenshots=cleaned_data.get("url_screenshots", []),
        )
        cleaned_data.update({"path_screenshots": path_screenshots})

    if (
        cleaned_data.get("ss_id", "")
        and int(cleaned_data.get("ss_id", "")) != rom.ss_id
    ):
        ss_rom = await meta_ss_handler.get_rom_by_id(cleaned_data["ss_id"])
        cleaned_data.update(ss_rom)
        path_screenshots = await fs_resource_handler.get_rom_screenshots(
            rom=rom,
            url_screenshots=cleaned_data.get("url_screenshots", []),
        )
        cleaned_data.update({"path_screenshots": path_screenshots})

    if (
        cleaned_data.get("igdb_id", "")
        and int(cleaned_data.get("igdb_id", "")) != rom.igdb_id
    ):
        igdb_rom = await meta_igdb_handler.get_rom_by_id(cleaned_data["igdb_id"])
        cleaned_data.update(igdb_rom)
        path_screenshots = await fs_resource_handler.get_rom_screenshots(
            rom=rom,
            url_screenshots=cleaned_data.get("url_screenshots", []),
        )
        cleaned_data.update({"path_screenshots": path_screenshots})

    if (
        cleaned_data.get("launchbox_id", "")
        and int(cleaned_data.get("launchbox_id", "")) != rom.launchbox_id
    ):
        igdb_rom = await meta_launchbox_handler.get_rom_by_id(
            cleaned_data["launchbox_id"]
        )
        cleaned_data.update(igdb_rom)
        path_screenshots = await fs_resource_handler.get_rom_screenshots(
            rom=rom,
            url_screenshots=cleaned_data.get("url_screenshots", []),
        )
        cleaned_data.update({"path_screenshots": path_screenshots})

    cleaned_data.update(
        {
            "name": data.get("name", rom.name),
            "summary": data.get("summary", rom.summary),
        }
    )

    new_fs_name = str(data.get("fs_name") or rom.fs_name)
    cleaned_data.update(
        {
            "fs_name": new_fs_name,
            "fs_name_no_tags": fs_rom_handler.get_file_name_with_no_tags(new_fs_name),
            "fs_name_no_ext": fs_rom_handler.get_file_name_with_no_extension(
                new_fs_name
            ),
        }
    )

    if remove_cover:
        cleaned_data.update(await fs_resource_handler.remove_cover(rom))
        cleaned_data.update({"url_cover": ""})
    else:
        if artwork is not None and artwork.filename is not None:
            file_ext = artwork.filename.split(".")[-1]
            artwork_content = BytesIO(await artwork.read())
            (
                path_cover_l,
                path_cover_s,
            ) = await fs_resource_handler.store_artwork(rom, artwork_content, file_ext)

            cleaned_data.update(
                {
                    "url_cover": "",
                    "path_cover_s": path_cover_s,
                    "path_cover_l": path_cover_l,
                }
            )
        else:
            if data.get(
                "url_cover", ""
            ) != rom.url_cover or not fs_resource_handler.cover_exists(
                rom, CoverSize.BIG
            ):
                path_cover_s, path_cover_l = await fs_resource_handler.get_cover(
                    entity=rom,
                    overwrite=True,
                    url_cover=str(data.get("url_cover") or ""),
                )
                cleaned_data.update(
                    {
                        "url_cover": data.get("url_cover", rom.url_cover),
                        "path_cover_s": path_cover_s,
                        "path_cover_l": path_cover_l,
                    }
                )

    if data.get(
        "url_manual", ""
    ) != rom.url_manual or not fs_resource_handler.manual_exists(rom):
        path_manual = await fs_resource_handler.get_manual(
            rom=rom,
            overwrite=True,
            url_manual=str(data.get("url_manual") or ""),
        )
        cleaned_data.update(
            {
                "url_manual": data.get("url_manual", rom.url_manual),
                "path_manual": path_manual,
            }
        )

    log.debug(
        f"Updating {hl(cleaned_data.get('name', ''), color=BLUE)} [{hl(cleaned_data.get('fs_name', ''))}] with data {cleaned_data}"
    )

    db_rom_handler.update_rom(id, cleaned_data)

    # Rename the file/folder if the name has changed
    should_update_fs = new_fs_name != rom.fs_name
    if should_update_fs:
        try:
            new_fs_name = sanitize_filename(new_fs_name)
            await fs_rom_handler.rename_fs_rom(
                old_name=rom.fs_name,
                new_name=new_fs_name,
                fs_path=rom.fs_path,
            )
        except RomAlreadyExistsException as exc:
            log.error(exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc
            ) from exc

    # Update the rom files with the new fs_name
    if should_update_fs:
        for file in rom.files:
            db_rom_handler.update_rom_file(
                file.id,
                {
                    "file_name": file.file_name.replace(rom.fs_name, new_fs_name),
                    "file_path": file.file_path.replace(rom.fs_name, new_fs_name),
                },
            )

    # Refetch the rom from the database
    rom = db_rom_handler.get_rom(id)
    if not rom:
        raise RomNotFoundInDatabaseException(id)

    return DetailedRomSchema.from_orm_with_request(rom, request)


@protected_route(
    router.post,
    "/{id}/manuals",
    [Scope.ROMS_WRITE],
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def add_rom_manuals(
    request: Request,
    id: Annotated[int, PathVar(description="Rom internal id.", ge=1)],
    filename: Annotated[
        str,
        Header(
            description="The name of the file being uploaded.",
            alias="x-upload-filename",
        ),
    ],
) -> Response:
    """Upload manuals for a rom."""

    rom = db_rom_handler.get_rom(id)
    if not rom:
        raise RomNotFoundInDatabaseException(id)

    manuals_path = f"{rom.fs_resources_path}/manual"
    file_location = fs_rom_handler.validate_path(f"{manuals_path}/{rom.id}.pdf")
    log.info(f"Uploading manual to {hl(str(file_location))}")

    await fs_rom_handler.make_directory(manuals_path)

    parser = StreamingFormDataParser(headers=request.headers)
    parser.register("x-upload-platform", NullTarget())
    parser.register(filename, FileTarget(str(file_location)))

    def cleanup_partial_file():
        if file_location.exists():
            file_location.unlink()

    try:
        async for chunk in request.stream():
            parser.data_received(chunk)
    except ClientDisconnect:
        log.error("Client disconnected during upload")
        cleanup_partial_file()
    except Exception as exc:
        log.error("Error uploading files", exc_info=exc)
        cleanup_partial_file()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="There was an error uploading the manual",
        ) from exc

    path_manual = await fs_resource_handler.get_manual(
        rom=rom, overwrite=False, url_manual=None
    )

    db_rom_handler.update_rom(
        id,
        {
            "path_manual": path_manual,
        },
    )

    return Response()


@protected_route(
    router.post,
    "/delete",
    [Scope.ROMS_WRITE],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def delete_roms(
    request: Request,
    roms: Annotated[
        list[int],
        Body(description="List of rom ids to delete from database."),
    ],
    delete_from_fs: Annotated[
        list[int],
        Body(
            description="List of rom ids to delete from filesystem.",
            default_factory=list,
        ),
    ],
) -> MessageResponse:
    """Delete roms."""

    for id in roms:
        rom = db_rom_handler.get_rom(id)

        if not rom:
            raise RomNotFoundInDatabaseException(id)

        log.info(
            f"Deleting {hl(str(rom.name or 'ROM'), color=BLUE)} [{hl(rom.fs_name)}] from database"
        )
        db_rom_handler.delete_rom(id)

        try:
            await fs_resource_handler.remove_directory(rom.fs_resources_path)
        except FileNotFoundError:
            log.warning(
                f"Couldn't find resources to delete for {hl(str(rom.name or 'ROM'), color=BLUE)}"
            )

        if id in delete_from_fs:
            log.info(f"Deleting {hl(rom.fs_name)} from filesystem")
            try:
                file_path = f"{rom.fs_path}/{rom.fs_name}"
                await fs_rom_handler.remove_file(file_path=file_path)
            except FileNotFoundError as exc:
                error = f"Rom file {hl(rom.fs_name)} not found for platform {hl(rom.platform_display_name, color=BLUE)}[{hl(rom.platform_slug)}]"
                log.error(error)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=error
                ) from exc

    return {"msg": f"{len(roms)} roms deleted successfully!"}


@protected_route(
    router.put,
    "/{id}/props",
    [Scope.ROMS_USER_WRITE],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def update_rom_user(
    request: Request,
    id: Annotated[int, PathVar(description="Rom internal id.", ge=1)],
    update_last_played: Annotated[
        bool,
        Body(description="Whether to update the last played date."),
    ] = False,
    remove_last_played: Annotated[
        bool,
        Body(description="Whether to remove the last played date."),
    ] = False,
) -> RomUserSchema:
    """Update rom data associated to the current user."""

    # TODO: Migrate to native FastAPI body parsing.
    data = await request.json()
    rom_user_data = data.get("data", {})

    rom = db_rom_handler.get_rom(id)

    if not rom:
        raise RomNotFoundInDatabaseException(id)

    db_rom_user = db_rom_handler.get_rom_user(
        id, request.user.id
    ) or db_rom_handler.add_rom_user(id, request.user.id)

    fields_to_update = [
        "note_raw_markdown",
        "note_is_public",
        "is_main_sibling",
        "backlogged",
        "now_playing",
        "hidden",
        "rating",
        "difficulty",
        "completion",
        "status",
    ]

    cleaned_data = {
        field: rom_user_data[field]
        for field in fields_to_update
        if field in rom_user_data
    }

    if update_last_played:
        cleaned_data.update({"last_played": datetime.now(timezone.utc)})
    elif remove_last_played:
        cleaned_data.update({"last_played": None})

    rom_user = db_rom_handler.update_rom_user(db_rom_user.id, cleaned_data)

    return RomUserSchema.model_validate(rom_user)


@protected_route(
    router.get,
    "files/{id}",
    [Scope.ROMS_READ],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def get_romfile(
    request: Request,
    id: Annotated[int, PathVar(description="Rom file internal id.", ge=1)],
) -> RomFileSchema:
    """Retrieve a rom file by ID."""

    file = db_rom_handler.get_rom_file_by_id(id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    return RomFileSchema.model_validate(file)


@protected_route(
    router.get,
    "files/{id}/content/{file_name}",
    [] if DISABLE_DOWNLOAD_ENDPOINT_AUTH else [Scope.ROMS_READ],
    responses={status.HTTP_404_NOT_FOUND: {}},
)
async def get_romfile_content(
    request: Request,
    id: Annotated[int, PathVar(description="Rom file internal id.", ge=1)],
    file_name: Annotated[str, PathVar(description="File name to download")],
):
    """Download a rom file."""

    current_username = (
        request.user.username if request.user.is_authenticated else "unknown"
    )

    file = db_rom_handler.get_rom_file_by_id(id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    log.info(f"User {hl(current_username, color=BLUE)} is downloading {hl(file_name)}")

    # Serve the file directly in development mode for emulatorjs
    if DEV_MODE:
        rom_path = fs_rom_handler.validate_path(file.full_path)
        return FileResponse(
            path=rom_path,
            filename=file_name,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}; filename=\"{quote(file_name)}\"",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(file.file_size_bytes),
            },
        )

    # Otherwise proxy through nginx
    return FileRedirectResponse(
        download_path=Path(f"/library/{file.full_path}"),
    )
