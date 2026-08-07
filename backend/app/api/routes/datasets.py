"""Dataset upload, registry, and profiling endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.logging import get_logger
from app.schemas.dataset import DatasetListResponse, DatasetMeta, UploadResponse
from app.schemas.profile import ProfileResponse
from app.services.dataset_service import DatasetService, DatasetServiceError, get_dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"])
logger = get_logger(__name__)


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    service: DatasetService = Depends(get_dataset_service),
) -> UploadResponse:
    """Upload a CSV, Excel, or PDF dataset and auto-generate its profile."""
    try:
        meta = await service.upload(file)
    except DatasetServiceError as exc:
        logger.warning("Upload rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return UploadResponse(
        message="Dataset uploaded and profiled successfully",
        dataset=meta,
    )


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetListResponse:
    """List previously uploaded datasets."""
    datasets = service.list_datasets()
    return DatasetListResponse(count=len(datasets), datasets=datasets)


@router.get("/{dataset_id}/profile", response_model=ProfileResponse)
def get_dataset_profile(
    dataset_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> ProfileResponse:
    """Return the automatic profiling report for a dataset."""
    try:
        source = "cache" if service.has_profile(dataset_id) else "generated"
        profile = service.get_profile(dataset_id)
    except DatasetServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return ProfileResponse(profile=profile, source=source)


@router.post("/{dataset_id}/profile", response_model=ProfileResponse)
def refresh_dataset_profile(
    dataset_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> ProfileResponse:
    """Re-run profiling for an existing dataset."""
    try:
        profile = service.refresh_profile(dataset_id)
    except DatasetServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return ProfileResponse(
        message="Dataset profile refreshed",
        profile=profile,
        source="generated",
    )


@router.get("/{dataset_id}", response_model=DatasetMeta)
def get_dataset(
    dataset_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetMeta:
    """Fetch metadata for a single dataset."""
    try:
        return service.get_dataset(dataset_id)
    except DatasetServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: str,
    service: DatasetService = Depends(get_dataset_service),
) -> None:
    """Remove an uploaded dataset and its stored files."""
    try:
        service.delete_dataset(dataset_id)
    except DatasetServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
