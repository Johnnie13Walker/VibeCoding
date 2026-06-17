"""Read-only слой источников для финансового контура."""

from __future__ import annotations

import json
import re
from typing import Any

from apps.finansist.config import DEFAULT_CONFIG
from apps.finansist.schemas.finance import FinanceSource, FinanceSourceSnapshot

_URL_RE = re.compile(r"https?://\S+")


class FinanceSourceProvider:
    def __init__(self, *, env_data: dict[str, str] | None = None) -> None:
        self.env_data = dict(env_data or {})

    def build_snapshot(self, raw_sources: tuple[str | dict[str, Any], ...] = ()) -> FinanceSourceSnapshot:
        sources = tuple(self._load_catalog_sources() + [self._normalize_source(item) for item in raw_sources if item])
        google_docs_ready = any(
            source.source_type == "google_doc" and source.access_status == "ready" for source in sources
        )
        google_sheets_ready = any(
            source.source_type == "google_sheet" and source.access_status == "ready" for source in sources
        )
        missing: list[str] = []
        if any(source.source_type in {"google_doc", "google_sheet"} for source in sources) and not self._google_credentials_ready():
            missing.append(
                "Для Google Docs/Sheets не подтвержден credential path. Нужен один из env: "
                + ", ".join(DEFAULT_CONFIG.google_credential_env_candidates)
            )
        return FinanceSourceSnapshot(
            sources=sources,
            google_docs_access_ready=google_docs_ready,
            google_sheets_access_ready=google_sheets_ready,
            missing_requirements=tuple(dict.fromkeys(missing)),
        )

    def extract_urls(self, text: str) -> tuple[str, ...]:
        return tuple(match.group(0).rstrip(".,)") for match in _URL_RE.finditer(str(text or "")))

    def _load_catalog_sources(self) -> list[FinanceSource]:
        for env_name in DEFAULT_CONFIG.source_catalog_env_candidates:
            raw = str(self.env_data.get(env_name) or "").strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, list):
                continue
            return [self._normalize_source(item) for item in payload if item]
        return []

    def _normalize_source(self, raw: str | dict[str, Any]) -> FinanceSource:
        if isinstance(raw, str):
            location = raw.strip()
            source_type = self._infer_type(location, "")
            return self._build_source(
                name=self._default_name(source_type),
                source_type=source_type,
                location=location,
            )

        name = str(raw.get("name") or "").strip()
        location = str(raw.get("location") or raw.get("url") or raw.get("path") or "").strip()
        declared_type = str(raw.get("source_type") or raw.get("type") or "").strip().lower()
        source_type = self._infer_type(location, declared_type)
        return self._build_source(
            name=name or self._default_name(source_type),
            source_type=source_type,
            location=location,
            explicit_status=str(raw.get("access_status") or "").strip().lower(),
            notes=str(raw.get("notes") or "").strip(),
        )

    def _build_source(
        self,
        *,
        name: str,
        source_type: str,
        location: str,
        explicit_status: str = "",
        notes: str = "",
    ) -> FinanceSource:
        if explicit_status:
            access_status = explicit_status
        elif source_type in {"google_doc", "google_sheet"}:
            access_status = "ready" if self._google_credentials_ready() else "needs_credentials"
        elif source_type in {"excel", "csv", "bitrix24"}:
            access_status = "ready"
        else:
            access_status = "detected"
        return FinanceSource(
            name=name,
            source_type=source_type,
            location=location,
            access_status=access_status,
            notes=notes,
        )

    def _infer_type(self, location: str, declared_type: str) -> str:
        lowered_location = str(location or "").strip().lower()
        lowered_type = declared_type.lower()
        if lowered_type in {
            "google_doc",
            "google_sheet",
            "excel",
            "csv",
            "bitrix24",
        }:
            return lowered_type
        if "docs.google.com" in lowered_location and "/document/" in lowered_location:
            return "google_doc"
        if "docs.google.com" in lowered_location and "/spreadsheets/" in lowered_location:
            return "google_sheet"
        if "bitrix24" in lowered_location:
            return "bitrix24"
        if lowered_location.endswith(".xlsx") or lowered_location.endswith(".xls"):
            return "excel"
        if lowered_location.endswith(".csv"):
            return "csv"
        return lowered_type or "unknown"

    def _default_name(self, source_type: str) -> str:
        mapping = {
            "google_doc": "Google Doc",
            "google_sheet": "Google Sheet",
            "excel": "Excel",
            "csv": "CSV",
            "bitrix24": "Bitrix24",
            "unknown": "Источник",
        }
        return mapping.get(source_type, "Источник")

    def _google_credentials_ready(self) -> bool:
        return any(str(self.env_data.get(env_name) or "").strip() for env_name in DEFAULT_CONFIG.google_credential_env_candidates)
