"""Persists uploaded PDF bytes and reads them back, via either backend
selected by settings.storage_backend (see app.core.config for why "local"
only works when the API and worker share a filesystem).
"""

import uuid
from pathlib import Path

from app.core.config import settings

BLOB_URI_PREFIX = "azure-blob://"


def save_document_bytes(document_id: uuid.UUID, file_bytes: bytes) -> str:
    if settings.storage_backend == "azure_blob":
        return _save_to_blob(document_id, file_bytes)
    return _save_to_local(document_id, file_bytes)


def read_document_bytes(storage_path: str) -> bytes:
    if storage_path.startswith(BLOB_URI_PREFIX):
        return _read_from_blob(storage_path)
    return Path(storage_path).read_bytes()


def _save_to_local(document_id: uuid.UUID, file_bytes: bytes) -> str:
    storage_dir = Path(settings.documents_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{document_id}.pdf"
    storage_path.write_bytes(file_bytes)
    return str(storage_path)


def _blob_name(document_id: uuid.UUID) -> str:
    return f"{document_id}.pdf"


def _save_to_blob(document_id: uuid.UUID, file_bytes: bytes) -> str:
    from azure.storage.blob import BlobServiceClient

    client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    container = client.get_container_client(settings.documents_blob_container)
    blob_name = _blob_name(document_id)
    container.upload_blob(blob_name, file_bytes, overwrite=True)
    return f"{BLOB_URI_PREFIX}{settings.documents_blob_container}/{blob_name}"


def _read_from_blob(storage_path: str) -> bytes:
    from azure.storage.blob import BlobServiceClient

    _, _, rest = storage_path.partition(BLOB_URI_PREFIX)
    container_name, _, blob_name = rest.partition("/")
    client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    container = client.get_container_client(container_name)
    return container.download_blob(blob_name).readall()
