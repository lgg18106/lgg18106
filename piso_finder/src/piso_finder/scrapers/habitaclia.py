from __future__ import annotations

from typing import Iterable

from ..models import Property
from .base import BaseScraper


class HabitacliaScraper(BaseScraper):
    """Habitaclia tiene cobertura limitada en Málaga capital.

    Mantenido como stub para completitud; desactivar en config si el mercado
    que buscas no aparece aquí.
    """

    BASE_URL = "https://www.habitaclia.com"
    NAME = "habitaclia"

    def search(self, criteria: dict, zones: dict) -> Iterable[Property]:
        return
        yield  # pragma: no cover
