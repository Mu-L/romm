from datetime import datetime

from models.platform import DEFAULT_COVER_ASPECT_RATIO
from pydantic import Field, computed_field, field_validator

from .base import BaseModel
from .firmware import FirmwareSchema


class PlatformSchema(BaseModel):
    id: int
    slug: str
    fs_slug: str
    rom_count: int
    name: str
    custom_name: str | None = None
    igdb_id: int | None = None
    sgdb_id: int | None = None
    moby_id: int | None = None
    ss_id: int | None = None
    igdb_slug: str | None
    moby_slug: str | None
    category: str | None = None
    generation: int | None = None
    family_name: str | None = None
    family_slug: str | None = None
    url_logo: str | None = None
    firmware: list[FirmwareSchema] = Field(default_factory=list)
    aspect_ratio: str = DEFAULT_COVER_ASPECT_RATIO
    created_at: datetime
    updated_at: datetime
    fs_size_bytes: int

    class Config:
        from_attributes = True

    @computed_field  # type: ignore
    @property
    def display_name(self) -> str:
        return self.custom_name or self.name

    @field_validator("firmware")
    def sort_files(cls, v: list[FirmwareSchema]) -> list[FirmwareSchema]:
        return sorted(v, key=lambda x: x.file_name)
