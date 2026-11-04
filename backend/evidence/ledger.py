"""Insertion-ordered evidence storage for one investigation."""

from pydantic import JsonValue

from backend.evidence.models import EvidenceRecord


class EvidenceLedger:
    """Store independent copies; duplicate IDs raise ValueError."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    def add(self, record: EvidenceRecord) -> None:
        """Append a record without overwriting existing evidence."""
        if record.id in self._records:
            raise ValueError(f"duplicate evidence ID: {record.id}")
        self._records[record.id] = record.model_copy(deep=True)

    def get(self, evidence_id: str) -> EvidenceRecord:
        """Retrieve an independent copy; unknown IDs raise KeyError."""
        return self._records[evidence_id].model_copy(deep=True)

    def list_all(self) -> list[EvidenceRecord]:
        """Return independent copies in insertion order."""
        return [record.model_copy(deep=True) for record in self._records.values()]

    def export(self) -> list[dict[str, JsonValue]]:
        """Export all records in insertion order with JSON-compatible values."""
        return [record.model_dump(mode="json") for record in self._records.values()]
