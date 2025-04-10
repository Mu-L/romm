from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import pydash
from handler.metadata.igdb_handler import SLUG_TO_IGDB_PLATFORM
from handler.metadata.moby_handler import SLUG_TO_MOBY_PLATFORM
from models.base import BaseModel
from models.rom import Rom
from sqlalchemy import String, func, select
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

if TYPE_CHECKING:
    from models.firmware import Firmware


DEFAULT_COVER_ASPECT_RATIO = "2 / 3"


class Platform(BaseModel):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    igdb_id: Mapped[int | None]
    sgdb_id: Mapped[int | None]
    moby_id: Mapped[int | None]
    ss_id: Mapped[int | None]
    slug: Mapped[str] = mapped_column(String(length=100))
    fs_slug: Mapped[str] = mapped_column(String(length=100))
    name: Mapped[str] = mapped_column(String(length=400))
    custom_name: Mapped[str | None] = mapped_column(String(length=400), default="")
    category: Mapped[str | None] = mapped_column(String(length=100), default="")
    generation: Mapped[int | None]
    family_name: Mapped[str | None] = mapped_column(String(length=1000), default="")
    family_slug: Mapped[str | None] = mapped_column(String(length=1000), default="")
    url_logo: Mapped[str | None] = mapped_column(String(length=1000), default="")

    roms: Mapped[list[Rom]] = relationship(back_populates="platform")
    firmware: Mapped[list[Firmware]] = relationship(
        lazy="selectin", back_populates="platform"
    )

    aspect_ratio: Mapped[str] = mapped_column(
        String(length=10), server_default=DEFAULT_COVER_ASPECT_RATIO
    )

    # Temp column to store the old slug from the migration
    temp_old_slug: Mapped[str | None] = mapped_column(String(length=100), default=None)

    # This runs a subquery to get the count of roms for the platform
    rom_count = column_property(
        select(func.count(Rom.id)).where(Rom.platform_id == id).scalar_subquery()
    )

    def __repr__(self) -> str:
        return self.name

    @cached_property
    def igdb_slug(self) -> str | None:
        return pydash.get(SLUG_TO_IGDB_PLATFORM, f"{self.slug}.igdb_slug", None)

    @cached_property
    def moby_slug(self) -> str | None:
        return pydash.get(SLUG_TO_MOBY_PLATFORM, f"{self.slug}.moby_slug", None)

    @cached_property
    def fs_size_bytes(self) -> int:
        from handler.database import db_stats_handler

        return db_stats_handler.get_platform_filesize(self.id)
