import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.documents import storage


def test_local_backend_round_trips_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "documents_storage_dir", str(tmp_path))

    document_id = uuid.uuid4()
    storage_path = storage.save_document_bytes(document_id, b"%PDF-fake-bytes")

    assert storage_path == str(tmp_path / f"{document_id}.pdf")
    assert storage.read_document_bytes(storage_path) == b"%PDF-fake-bytes"


def test_local_backend_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        storage.read_document_bytes(str(tmp_path / "nonexistent.pdf"))


class _FakeDownloadStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeContainerClient:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def upload_blob(self, name: str, data: bytes, overwrite: bool = False) -> None:
        self.blobs[name] = data

    def download_blob(self, name: str) -> _FakeDownloadStream:
        return _FakeDownloadStream(self.blobs[name])


class _FakeBlobServiceClient:
    # Shared across instances so a client built for the write and a
    # separate one built for the read see the same uploaded blobs, mirroring
    # a real Azure Storage account.
    _container = _FakeContainerClient()

    @classmethod
    def from_connection_string(cls, conn_str: str) -> "_FakeBlobServiceClient":
        assert conn_str == "fake-connection-string"
        return cls()

    def get_container_client(self, name: str) -> _FakeContainerClient:
        assert name == "documents"
        return _FakeBlobServiceClient._container


def test_azure_blob_backend_round_trips_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "storage_backend", "azure_blob")
    monkeypatch.setattr(settings, "azure_storage_connection_string", "fake-connection-string")
    monkeypatch.setattr(settings, "documents_blob_container", "documents")
    monkeypatch.setattr("azure.storage.blob.BlobServiceClient", _FakeBlobServiceClient)

    document_id = uuid.uuid4()
    storage_path = storage.save_document_bytes(document_id, b"%PDF-fake-bytes")

    assert storage_path == f"azure-blob://documents/{document_id}.pdf"
    assert storage.read_document_bytes(storage_path) == b"%PDF-fake-bytes"
