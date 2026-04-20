from __future__ import annotations
#graph_mapper_agent/adapters/tools/ingest_storage.py
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import mimetypes
from urllib.parse import urlparse


GRAPH_MAPPER_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = GRAPH_MAPPER_ROOT / "data"
INGEST_ROOT = DATA_ROOT / "ingest"
LEDGER_ROOT = DATA_ROOT / "ledger"


@dataclass(frozen=True)
class SavedDocument:
    """
    Local result of saving an original document into storage.
    """
    original_path: str
    filename: str
    content_type: str | None
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class StorageScope:
    namespace: str = "graph_mapper_agent"
    session_id: str | None = None
    run_id: str | None = None
    jurisdiction_code: str | None = None
    document_key: str | None = None


class IngestStorage:
    """
    Filesystem helper for the document ingestion lane.

    Responsibilities:
    - resolve the live document folder
    - decide the original file path
    - save bytes
    - compute hash
    """

    def document_root(
        self,
        jurisdiction_code: str,
        document_key: str,
    ) -> Path:
        return (
            INGEST_ROOT
            / jurisdiction_code
            / "working"
            / "staging"
            / document_key
        )

    def scoped_document_root(self, scope: StorageScope) -> Path:
        session_id = str(scope.session_id or "").strip()
        run_id = str(scope.run_id or "").strip()
        namespace = str(scope.namespace or "graph_mapper_agent").strip() or "graph_mapper_agent"

        if session_id and run_id:
            return (
                INGEST_ROOT
                / namespace
                / "sessions"
                / session_id
                / "runs"
                / run_id
            )

        if run_id:
            return INGEST_ROOT / namespace / "runs" / run_id

        if session_id:
            return INGEST_ROOT / namespace / "sessions" / session_id

        jurisdiction_code = str(scope.jurisdiction_code or "").strip()
        document_key = str(scope.document_key or "").strip()
        if jurisdiction_code and document_key:
            return self.document_root(jurisdiction_code, document_key)

        return INGEST_ROOT / namespace / "ad_hoc"

    def original_dir(
        self,
        jurisdiction_code: str,
        document_key: str,
    ) -> Path:
        root = self.document_root(jurisdiction_code, document_key)
        path = root / "original"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def scoped_original_dir(self, scope: StorageScope) -> Path:
        root = self.scoped_document_root(scope)
        path = root / "original"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_original_bytes(
        self,
        jurisdiction_code: str,
        document_key: str,
        source_url: str,
        content: bytes,
        filename: str | None = None,
        content_type: str | None = None,
        scope: StorageScope | None = None,
    ) -> SavedDocument:
        if scope is not None:
            original_dir = self.scoped_original_dir(scope)
        else:
            original_dir = self.original_dir(jurisdiction_code, document_key)

        resolved_filename = filename or self._infer_filename(source_url, content_type)
        destination = original_dir / resolved_filename
        destination.write_bytes(content)

        digest = sha256(content).hexdigest()
        detected_content_type = content_type or mimetypes.guess_type(destination.name)[0]

        return SavedDocument(
            original_path=str(destination.relative_to(GRAPH_MAPPER_ROOT)),
            filename=destination.name,
            content_type=detected_content_type,
            sha256=digest,
            size_bytes=len(content),
        )

    @staticmethod
    def _infer_filename(source_url: str, content_type: str | None) -> str:
        parsed = urlparse(source_url)
        name = Path(parsed.path).name.strip()
        if name:
            return name

        if content_type:
            guessed_ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if guessed_ext:
                return f"document{guessed_ext}"

        return "document.bin"