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


ZONE_SLUGS = {
    ("Torremolinos", "Playamar"): "torremolinos/playamar-el-pinillo",
    ("Torremolinos", "Los Álamos"): "torremolinos/los-alamos",
    ("Torremolinos", "El Pinar"): "torremolinos/el-pinar",
    ("Mijas", "Las Lagunas"): "mijas/las-lagunas",
    ("Mijas", "La Cala de Mijas"): "mijas/la-cala",
    ("Fuengirola", "Torreblanca"): "fuengirola/torreblanca-del-sol",
    ("Fuengirola", "Los Boliches"): "fuengirola/los-boliches",
    ("Fuengirola", "Carvajal"): "fuengirola/carvajal",
    ("Rincón de la Victoria", "Cotomar"): "rincon-de-la-victoria/cotomar",
    ("Rincón de la Victoria", "Añoreta"): "rincon-de-la-victoria/anoreta",
    ("Benalmádena", "Arroyo de la Miel"): "benalmadena/arroyo-de-la-miel",
    ("Benalmádena", "Costa"): "benalmadena/benalmadena-costa",
}


class FotocasaScraper(BaseScraper):
    BASE_URL = "https://www.fotocasa.es"
    NAME = "fotocasa"

    def _path(self, slug: str, criteria: dict, page: int) -> str:
        pmin, pmax = criteria["price_min"], criteria["price_max"]
        rmin = criteria["rooms_min"]
        amin = criteria["area_min_m2"]
        base = f"/es/comprar/viviendas/{slug}/l"
        qs = (
            f"?minPrice={pmin}&maxPrice={pmax}"
            f"&minRooms={rmin}&minSurface={amin}"
            "&features[]=swimmingPool&features[]=parking&features[]=lift"
        )
        if page > 1:
            qs += f"&combinedLocationIds=&pagination={page}"
        return base + qs

    def _parse_card(self, card) -> Optional[Property]:
        try:
            a = card.select_one("a")
            href = a.get("href") if a else ""
            url = self.BASE_URL + href if href.startswith("/") else href
            title = a.get_text(" ", strip=True) if a else ""
            price_el = card.select_one("[data-testid='price'], .re-CardPrice, span[class*='Price']")
            price = parse_int_euro(price_el.get_text()) if price_el else None
            if not price:
                return None
            text = card.get_text(" ", strip=True)
            return Property(
                source=self.NAME,
                url=url,
                title=title[:200],
                price=price,
                municipio=self._guess_municipio(url),
                barrio=self._guess_barrio(url),
                rooms=parse_rooms(text),
                area_m2=parse_area_m2(text),
                has_garage=has_keyword(text, "garaje", "parking"),
                has_pool=has_keyword(text, "piscina"),
                has_elevator=has_keyword(text, "ascensor"),
                has_terrace=has_keyword(text, "terraza"),
                is_exterior=has_keyword(text, "exterior"),
                is_new_build=has_keyword(text, "obra nueva", "a estrenar", "promoción"),
                energy_cert=detect_energy_cert(text),
                state_flags=detect_state_flags(text),
                description=text[:500],
            )
        except Exception:
            return None

    def _guess_municipio(self, url: str) -> str:
        for (mun, _), slug in ZONE_SLUGS.items():
            if slug.split("/")[0] in url:
                return mun
        return "Málaga"

    def _guess_barrio(self, url: str) -> Optional[str]:
        for (_, barrio), slug in ZONE_SLUGS.items():
            if slug in url:
                return barrio
        return None

    def search(self, criteria: dict, zones: dict) -> Iterable[Property]:
        for zone in zones.get("priority_1", []) + zones.get("priority_2", []):
            key = (zone["municipio"], zone.get("barrio"))
            slug = ZONE_SLUGS.get(key)
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
                cards = soup.select("article, div[class*='PropertyCard'], li[class*='re-Card']")
                if not cards:
                    break
                for card in cards:
                    prop = self._parse_card(card)
                    if prop:
                        yield prop
