from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from ..models import Property
from .base import BaseScraper


class LocalFileScraper(BaseScraper):
    """Lee anuncios desde un JSON o CSV local.

    Útil para:
      - Procesar dumps exportados manualmente desde portales.
      - Alimentar el pipeline con resultados obtenidos por Playwright
        desde la máquina del usuario (donde sí pasa el antibot).
      - Trabajar con datasets públicos de Kaggle/GitHub.

    Formato JSON: lista de objetos con las claves del Property.
    Formato CSV: misma lista con cabecera.
    """

    NAME = "local_file"

    def _read_json(self, path: Path) -> list[dict]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("items", [])

    def _read_csv(self, path: Path) -> list[dict]:
        with path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def search(self, criteria: dict, zones: dict) -> Iterable[Property]:
        paths = self.cfg.get("paths", [])
        if isinstance(paths, str):
            paths = [paths]
        for p in paths:
            path = Path(p)
            if not path.exists():
                continue
            rows = self._read_json(path) if path.suffix.lower() == ".json" else self._read_csv(path)
            for row in rows:
                yield self._row_to_property(row)

    def _row_to_property(self, row: dict) -> Property:
        def _bool(v):
            if isinstance(v, bool):
                return v
            if v is None:
                return False
            return str(v).strip().lower() in {"true", "1", "sí", "si", "yes"}

        def _num(v, cast=float):
            if v in (None, ""):
                return None
            try:
                return cast(v)
            except (ValueError, TypeError):
                return None

        flags = row.get("state_flags") or []
        if isinstance(flags, str):
            flags = [f.strip() for f in flags.split(",") if f.strip()]

        return Property(
            source=row.get("source", self.NAME),
            url=row.get("url", ""),
            title=row.get("title", ""),
            price=_num(row.get("price")) or 0.0,
            municipio=row.get("municipio", ""),
            barrio=row.get("barrio"),
            rooms=_num(row.get("rooms"), int),
            bathrooms=_num(row.get("bathrooms"), int),
            area_m2=_num(row.get("area_m2")),
            has_garage=_bool(row.get("has_garage")),
            has_pool=_bool(row.get("has_pool")),
            has_elevator=_bool(row.get("has_elevator")),
            has_terrace=_bool(row.get("has_terrace")),
            is_exterior=_bool(row.get("is_exterior")),
            orientation=row.get("orientation"),
            is_new_build=_bool(row.get("is_new_build")),
            energy_cert=row.get("energy_cert"),
            state_flags=list(flags),
            description=row.get("description"),
        )
