"""Pydantic schemas for API requests and responses."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.models.asset_outcome import AssetOutcome as AssetOutcomeRow
from app.models.run import Run as RunRow
from app.models.settings import Settings as SettingsRow

# The ORM columns behind these fields are always written with
# datetime.now(timezone.utc), but SQLite/SQLAlchemy drops the tzinfo on
# read, so the value we get here is UTC without saying so. Serializing it
# as-is produces an offset-less ISO string (e.g. "2026-09-23T22:00:01"),
# which browsers parse as local time instead of converting it -- the run
# then appears to have started two hours earlier than it actually did.
# Stamp the UTC offset back on before it leaves the API.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(
        lambda dt: (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat(),
        return_type=str,
    ),
]


class SettingsResponse(BaseModel):
    """Settings as returned to the client. The API key is masked."""

    model_config = ConfigDict(from_attributes=True)

    immich_api_base: str
    immich_api_key_set: bool
    asset_types: str
    include_archived: bool
    include_deleted: bool
    convert_image_formats: str
    image_target_format: str
    image_distance: float
    image_distance_retry: float
    image_jxl_effort: int
    image_quality_heic: int
    image_quality_heic_retry: int
    image_quality_avif: int
    image_quality_avif_retry: int
    video_crf: int
    video_preset: int
    video_max_dimension: int
    video_audio_bitrate: str
    video_crf_retry: int
    enable_retry: bool
    accept_retry_output: bool
    allow_larger: bool
    concurrency: int
    output_mode: str
    local_output_dir: str
    local_keep_originals: bool

    @classmethod
    def from_settings(cls, settings: SettingsRow) -> "SettingsResponse":
        return cls(
            immich_api_base=settings.immich_api_base,
            immich_api_key_set=bool(settings.immich_api_key),
            asset_types=settings.asset_types,
            include_archived=settings.include_archived,
            include_deleted=settings.include_deleted,
            convert_image_formats=settings.convert_image_formats,
            image_target_format=settings.image_target_format,
            image_distance=settings.image_distance,
            image_distance_retry=settings.image_distance_retry,
            image_jxl_effort=settings.image_jxl_effort,
            image_quality_heic=settings.image_quality_heic,
            image_quality_heic_retry=settings.image_quality_heic_retry,
            image_quality_avif=settings.image_quality_avif,
            image_quality_avif_retry=settings.image_quality_avif_retry,
            video_crf=settings.video_crf,
            video_preset=settings.video_preset,
            video_max_dimension=settings.video_max_dimension,
            video_audio_bitrate=settings.video_audio_bitrate,
            video_crf_retry=settings.video_crf_retry,
            enable_retry=settings.enable_retry,
            accept_retry_output=settings.accept_retry_output,
            allow_larger=settings.allow_larger,
            concurrency=settings.concurrency,
            output_mode=settings.output_mode,
            local_output_dir=settings.local_output_dir,
            local_keep_originals=settings.local_keep_originals,
        )


class SettingsUpdate(BaseModel):
    """Partial update for settings. Omitted fields are left unchanged.

    immich_api_key: pass null/omit to leave the stored key unchanged, or an
    empty string to clear it. This lets the UI round-trip the masked
    settings response without ever needing to redisplay the real key.
    """

    immich_api_base: str | None = None
    immich_api_key: str | None = None
    asset_types: str | None = None
    include_archived: bool | None = None
    include_deleted: bool | None = None
    convert_image_formats: str | None = None
    image_target_format: str | None = None
    image_distance: float | None = Field(default=None, ge=0, le=25)
    image_distance_retry: float | None = Field(default=None, ge=0, le=25)
    image_jxl_effort: int | None = Field(default=None, ge=1, le=10)
    image_quality_heic: int | None = Field(default=None, ge=0, le=100)
    image_quality_heic_retry: int | None = Field(default=None, ge=0, le=100)
    image_quality_avif: int | None = Field(default=None, ge=0, le=100)
    image_quality_avif_retry: int | None = Field(default=None, ge=0, le=100)
    video_crf: int | None = Field(default=None, ge=0, le=63)
    video_preset: int | None = Field(default=None, ge=0, le=13)
    video_max_dimension: int | None = Field(default=None, ge=0)
    video_audio_bitrate: str | None = None
    video_crf_retry: int | None = Field(default=None, ge=0, le=63)
    enable_retry: bool | None = None
    accept_retry_output: bool | None = None
    allow_larger: bool | None = None
    concurrency: int | None = Field(default=None, ge=1, le=32)
    output_mode: str | None = None
    local_output_dir: str | None = None
    local_keep_originals: bool | None = None


class TestConnectionRequest(BaseModel):
    """Optional override so the connection can be tested before saving."""

    immich_api_base: str | None = None
    immich_api_key: str | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    error: str | None = None
    server_version: str | None = None


class AssetItem(BaseModel):
    id: str
    original_file_name: str
    original_path: str
    original_mime_type: str | None
    type: str
    file_created_at: str
    file_modified_at: str
    already_jxl: bool


class AssetListResponse(BaseModel):
    items: list[AssetItem]
    page: int
    size: int
    has_more: bool


class AlbumItem(BaseModel):
    id: str
    album_name: str
    asset_count: int


class AlbumListResponse(BaseModel):
    items: list[AlbumItem]


class RunCreate(BaseModel):
    """Start a run either from an explicit asset selection or from filters."""

    asset_ids: list[str] | None = None

    asset_types: str | None = None
    album_id: str | None = None
    include_archived: bool | None = None
    include_deleted: bool | None = None
    taken_after: str | None = None
    taken_before: str | None = None
    original_filename: str | None = None
    max_assets: int | None = Field(default=None, ge=1)

    dry_run: bool = True

    convert_image_formats: str | None = None
    image_target_format: str | None = None
    image_distance: float | None = Field(default=None, ge=0, le=25)
    image_distance_retry: float | None = Field(default=None, ge=0, le=25)
    image_jxl_effort: int | None = Field(default=None, ge=1, le=10)
    image_quality_heic: int | None = Field(default=None, ge=0, le=100)
    image_quality_heic_retry: int | None = Field(default=None, ge=0, le=100)
    image_quality_avif: int | None = Field(default=None, ge=0, le=100)
    image_quality_avif_retry: int | None = Field(default=None, ge=0, le=100)
    video_crf: int | None = Field(default=None, ge=0, le=63)
    video_preset: int | None = Field(default=None, ge=0, le=13)
    video_max_dimension: int | None = Field(default=None, ge=0)
    video_audio_bitrate: str | None = None
    video_crf_retry: int | None = Field(default=None, ge=0, le=63)
    enable_retry: bool | None = None
    accept_retry_output: bool | None = None
    allow_larger: bool | None = None
    concurrency: int | None = Field(default=None, ge=1, le=32)
    output_mode: str | None = None
    local_output_dir: str | None = None
    local_keep_originals: bool | None = None


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    dry_run: bool
    total_assets: int
    processed_count: int
    success_count: int
    skipped_count: int
    failed_count: int
    input_bytes: int
    output_bytes: int
    error_message: str | None

    @classmethod
    def from_run(cls, run: RunRow) -> "RunResponse":
        return cls.model_validate(run)


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int


class AssetOutcomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: str
    filename: str
    status: str
    error: str | None
    new_asset_id: str | None
    target_format: str | None
    input_bytes: int
    output_bytes: int
    updated_at: UtcDatetime

    @classmethod
    def from_outcome(cls, outcome: AssetOutcomeRow) -> "AssetOutcomeResponse":
        return cls.model_validate(outcome)


class AssetOutcomeListResponse(BaseModel):
    items: list[AssetOutcomeResponse]
    total: int
