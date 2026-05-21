"""Orchestrator cho ingestion: storage -> loader -> chunker -> embedding -> DB.
Phase 2 (D16) + Phase 3 (D19)."""

from __future__ import annotations

# TODO D16: ingest_source(source_id: UUID) -> IngestResult
# TODO D16: idempotent qua sources.checksum (SHA256)
# TODO D24: failure handling + resumable status
