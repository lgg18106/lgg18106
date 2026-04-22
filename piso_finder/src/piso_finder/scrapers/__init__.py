from __future__ import annotations

from .base import BaseScraper
from .idealista import IdealistaScraper
from .fotocasa import FotocasaScraper
from .pisos_com import PisosComScraper
from .habitaclia import HabitacliaScraper
from .local_file import LocalFileScraper


SCRAPERS: dict[str, type[BaseScraper]] = {
    "idealista": IdealistaScraper,
    "fotocasa": FotocasaScraper,
    "pisos_com": PisosComScraper,
    "habitaclia": HabitacliaScraper,
    "local_file": LocalFileScraper,
}


def build_scraper(name: str, cfg: dict) -> BaseScraper:
    cls = SCRAPERS[name]
    return cls(cfg)
