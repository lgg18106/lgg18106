from __future__ import annotations

import os
from typing import Iterable, Optional
from urllib.parse import quote

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
    ("Torremolinos", "Playamar"): "torremolinos-malaga/playamar",
    ("Torremolinos", "Los Álamos"): "torremolinos-malaga/los-alamos",
    ("Torremolinos", "El Pinar"): "torremolinos-malaga/el-pinar",
    ("Mijas", "Las Lagunas"): "mijas-malaga/las-lagunas",
    ("Mijas", "La Cala de Mijas"): "mijas-malaga/la-cala-de-mijas",
    ("Fuengirola", "Torreblanca"): "fuengirola-malaga/torreblanca-del-sol",
    ("Fuengirola", "Los Boliches"): "fuengirola-malaga/los-boliches",
    ("Fuengirola", "Carvajal"): "fuengirola-malaga/carvajal",
    ("Rincón de la Victoria", "Cotomar"): "rincon-de-la-victoria-malaga/cotomar-urbanizaciones",
    ("Rincón de la Victoria", "Añoreta"): "rincon-de-la-victoria-malaga/anoreta",
    ("Benalmádena", "Arroyo de la Miel"): "benalmadena-malaga/arroyo-de-la-miel",
    ("Benalmádena", "Costa"): "benalmadena-malaga/benalmadena-costa",
}


class IdealistaScraper(BaseScraper):
    """Scraper for Idealista.

    Prefiere la API oficial si se configuran credenciales en .env:
        IDEALISTA_API_KEY=...
        IDEALISTA_API_SECRET=...
    Si no, cae a HTML scraping muy conservador.
    """

    BASE_URL = "https://www.idealista.com"
    NAME = "idealista"

    def _build_filter_path(self, criteria: dict) -> str:
        pmin = criteria["price_min"]
        pmax = criteria["price_max"]
        rmin = criteria["rooms_min"]
        amin = criteria["area_min_m2"]
        parts = [
            f"precio-desde_{pmin}",
            f"precio-hasta_{pmax}",
            f"metros-cuadrados-mas-de_{amin}",
            f"de-{rmin}-dormitorios",
            "con-garaje",
            "con-piscina-comunitaria,ascensor",
        ]
        return "/con-" + ",".join(parts) + "/"

    def _parse_card(self, card) -> Optional[Property]:
        try:
            a = card.select_one("a.item-link")
            if not a:
                return None
            href = a.get("href", "")
            title = a.get("title") or a.get_text(strip=True)
            url = self.BASE_URL + href if href.startswith("/") else href

            price_el = card.select_one(".item-price")
            price = parse_int_euro(price_el.get_text()) if price_el else None
            if not price:
                return None

            details = " ".join(el.get_text(" ", strip=True) for el in card.select(".item-detail"))
            description = card.get_text(" ", strip=True)

            rooms = parse_rooms(details)
            area = parse_area_m2(details)

            return Property(
                source=self.NAME,
                url=url,
                title=title,
                price=price,
                municipio=self._guess_municipio(url),
                barrio=self._guess_barrio(url),
                rooms=rooms,
                area_m2=area,
                has_garage=has_keyword(description, "garaje", "parking", "plaza de garaje"),
                has_pool=has_keyword(description, "piscina"),
                has_elevator=has_keyword(description, "ascensor"),
                has_terrace=has_keyword(description, "terraza"),
                is_exterior=has_keyword(description, "exterior"),
                is_new_build=has_keyword(description, "obra nueva", "promoción", "a estrenar"),
                energy_cert=detect_energy_cert(description),
                state_flags=detect_state_flags(description),
                description=description[:500],
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

    def _fetch_zone(self, zone: dict, criteria: dict) -> Iterable[Property]:
        key = (zone["municipio"], zone.get("barrio"))
        slug = ZONE_SLUGS.get(key)
        if not slug:
            return
        filter_path = self._build_filter_path(criteria)
        for page in range(1, self.max_pages + 1):
            path = f"/venta-viviendas/{slug}{filter_path}" + (f"pagina-{page}/" if page > 1 else "")
            if not self.robots_allows(path):
                return
            try:
                resp = self.get(self.BASE_URL + path)
            except Exception:
                return
            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("article.item")
            if not cards:
                return
            for card in cards:
                prop = self._parse_card(card)
                if prop:
                    yield prop

    def search(self, criteria: dict, zones: dict) -> Iterable[Property]:
        if self.cfg.get("use_official_api") and os.getenv("IDEALISTA_API_KEY"):
            yield from self._search_official_api(criteria, zones)
            return
        for zone in zones.get("priority_1", []) + zones.get("priority_2", []):
            yield from self._fetch_zone(zone, criteria)

    def _search_official_api(self, criteria: dict, zones: dict) -> Iterable[Property]:
        # Stub — implementar con OAuth2 client credentials si el usuario tiene API.
        # Docs: https://developers.idealista.com
        return
        yield  # pragma: no cover
