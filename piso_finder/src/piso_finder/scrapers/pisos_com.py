from __future__ import annotations

from typing import Iterable, Optional

from bs4 import BeautifulSoup

from ..models import Property
from ..normalize import (
    detect_energy_cert,
    detect_state_flags,
    has_keyword,
    parse_area_m2,
    parse_int_euro,
    parse_rooms,
)
from .base import BaseScraper


MUNICIPIO_SLUGS = {
    "Torremolinos": "torremolinos",
    "Mijas": "mijas",
    "Fuengirola": "fuengirola",
    "Rincón de la Victoria": "rincon-de-la-victoria",
    "Benalmádena": "benalmadena",
}


class PisosComScraper(BaseScraper):
    BASE_URL = "https://www.pisos.com"
    NAME = "pisos_com"

    def _path(self, municipio_slug: str, criteria: dict, page: int) -> str:
        pmin, pmax = criteria["price_min"], criteria["price_max"]
        rmin = criteria["rooms_min"]
        base = f"/viviendas-{municipio_slug}/"
        qs = (
            f"?precio-desde={pmin}&precio-hasta={pmax}&dormitorios-desde={rmin}"
            "&caracteristicas=piscina,garaje,ascensor"
        )
        if page > 1:
            qs += f"&pagina={page}"
        return base + qs

    def _parse_card(self, card) -> Optional[Property]:
        try:
            a = card.select_one("a.ad-preview__title, a[href*='/comprar/']")
            if not a:
                return None
            href = a.get("href", "")
            url = self.BASE_URL + href if href.startswith("/") else href
            title = a.get_text(" ", strip=True)
            price_el = card.select_one(".ad-preview__price, [class*='price']")
            price = parse_int_euro(price_el.get_text()) if price_el else None
            if not price:
                return None
            text = card.get_text(" ", strip=True)
            municipio = next(
                (m for m, s in MUNICIPIO_SLUGS.items() if s in url), "Málaga"
            )
            return Property(
                source=self.NAME,
                url=url,
                title=title[:200],
                price=price,
                municipio=municipio,
                rooms=parse_rooms(text),
                area_m2=parse_area_m2(text),
                has_garage=has_keyword(text, "garaje", "parking"),
                has_pool=has_keyword(text, "piscina"),
                has_elevator=has_keyword(text, "ascensor"),
                has_terrace=has_keyword(text, "terraza"),
                is_exterior=has_keyword(text, "exterior"),
                is_new_build=has_keyword(text, "obra nueva", "a estrenar"),
                energy_cert=detect_energy_cert(text),
                state_flags=detect_state_flags(text),
                description=text[:500],
            )
        except Exception:
            return None

    def search(self, criteria: dict, zones: dict) -> Iterable[Property]:
        municipios_seen: set[str] = set()
        for zone in zones.get("priority_1", []) + zones.get("priority_2", []):
            mun = zone["municipio"]
            if mun in municipios_seen:
                continue
            municipios_seen.add(mun)
            slug = MUNICIPIO_SLUGS.get(mun)
            if not slug:
                continue
            for page in range(1, self.max_pages + 1):
                path = self._path(slug, criteria, page)
                if not self.robots_allows(path):
                    break
                try:
                    resp = self.get(self.BASE_URL + path)
                except Exception:
                    break
                soup = BeautifulSoup(resp.text, "lxml")
                cards = soup.select(".ad-preview, article[class*='Card']")
                if not cards:
                    break
                for card in cards:
                    prop = self._parse_card(card)
                    if prop:
                        yield prop
