"""Fetcher de un anuncio concreto de Idealista usando Playwright.

Playwright con navegador real (Chromium headless) pasa el antibot de
Cloudflare/DataDome desde IPs residenciales, cosa que las peticiones
HTTP simples no consiguen.

La extracción se apoya, en orden de preferencia:
  1. JSON-LD schema.org embebido en la página (formato estable)
  2. Meta tags Open Graph
  3. Selectores CSS de la web de Idealista (pueden romper con redesigns)
  4. Text-mining de la descripción con los helpers de normalize.py
"""
from __future__ import annotations

import json
import re
from typing import Optional

from ..models import Property
from ..normalize import (
    detect_energy_cert,
    detect_state_flags,
    has_keyword,
    parse_area_m2,
    parse_int_euro,
    parse_rooms,
)


def _extract_ld_json(html: str) -> dict:
    """Devuelve el primer script application/ld+json parseado."""
    for m in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    ):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if isinstance(c, dict) and (
                c.get("@type") in {"Product", "Residence", "Apartment", "RealEstateListing"}
                or "offers" in c
            ):
                return c
    return {}


def _extract_meta(html: str, prop: str) -> Optional[str]:
    m = re.search(rf'<meta[^>]+property="{re.escape(prop)}"[^>]+content="([^"]*)"', html)
    return m.group(1) if m else None


def _parse_price_from_ld(ld: dict) -> Optional[float]:
    offers = ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("price") or offers.get("priceSpecification", {}).get("price")
    if price is None:
        return None
    return float(str(price).replace(",", ".").replace(" ", ""))


def _parse_address(ld: dict) -> tuple[str, Optional[str]]:
    addr = ld.get("address") or {}
    if isinstance(addr, list):
        addr = addr[0] if addr else {}
    locality = addr.get("addressLocality") or ""
    region = addr.get("addressRegion")
    barrio = addr.get("addressNeighborhood") or addr.get("addressSubLocality")
    return locality, barrio


def _parse_surface(ld: dict, html: str) -> Optional[float]:
    size = ld.get("floorSize") or {}
    if isinstance(size, dict):
        val = size.get("value")
        if val:
            try:
                return float(str(val).replace(",", "."))
            except ValueError:
                pass
    # fallback al texto
    return parse_area_m2(html)


def _detect_feature(html: str, ld_features: list[str], keywords: tuple[str, ...]) -> bool:
    text_ld = " ".join(ld_features).lower()
    if any(k in text_ld for k in keywords):
        return True
    return has_keyword(html, *keywords)


def _days_on_market(html: str) -> Optional[int]:
    m = re.search(r"anuncio\s+actualizado\s+el\s+(\d{1,2})\s+de\s+(\w+)", html, re.I)
    if m:
        # no calculamos fecha exacta; si el usuario la quiere precisa, que la pase por CLI
        return None
    m = re.search(r"actualizado\s+hace\s+(\d+)\s+d", html, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s+d[ií]as?\s+en\s+idealista", html, re.I)
    if m:
        return int(m.group(1))
    return None


def fetch_property(url: str, headless: bool = True, timeout_ms: int = 45000) -> Property:
    """Descarga la página con Playwright y devuelve un Property normalizado.

    Requiere haber ejecutado previamente:
        pip install playwright
        playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright no está instalado. Ejecuta:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from e

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1366, "height": 820},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        # Banner de cookies Idealista (Didomi)
        for sel in [
            "#didomi-notice-agree-button",
            "button:has-text('Aceptar')",
            "button:has-text('Aceptar y continuar')",
        ]:
            try:
                page.locator(sel).first.click(timeout=2500)
                break
            except Exception:
                continue

        page.wait_for_timeout(1500)
        html = page.content()
        browser.close()

    return _parse_html(url, html)


def _parse_html(url: str, html: str) -> Property:
    ld = _extract_ld_json(html)

    title = (
        ld.get("name")
        or _extract_meta(html, "og:title")
        or ""
    )
    description = (
        ld.get("description")
        or _extract_meta(html, "og:description")
        or ""
    )

    municipio, barrio = _parse_address(ld)
    if not municipio:
        m = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
        municipio = m.group(1) if m else ""

    price = _parse_price_from_ld(ld) or parse_int_euro(description) or 0.0
    area = _parse_surface(ld, description) or parse_area_m2(html)
    rooms = ld.get("numberOfRooms") or parse_rooms(description) or parse_rooms(html)
    bathrooms = ld.get("numberOfBathroomsTotal") or ld.get("numberOfBathroomsTotal")

    # ld can have amenityFeature list
    features = ld.get("amenityFeature") or []
    ld_feat_names = []
    if isinstance(features, list):
        for f in features:
            if isinstance(f, dict):
                ld_feat_names.append(str(f.get("name", "")))

    is_new_build = has_keyword(title + " " + description, "obra nueva", "a estrenar", "promoción")
    has_garage = _detect_feature(html, ld_feat_names, ("garaje", "parking", "plaza de garaje"))
    has_pool = _detect_feature(html, ld_feat_names, ("piscina",))
    has_elevator = _detect_feature(html, ld_feat_names, ("ascensor",))
    has_terrace = _detect_feature(html, ld_feat_names, ("terraza", "balcón", "balcon"))
    is_exterior = has_keyword(description, "exterior")
    orient_match = re.search(r"orientaci[oó]n\s*[:\-]?\s*(norte|sur|este|oeste|noreste|noroeste|sureste|suroeste)", html, re.I)
    orientation = orient_match.group(1).lower() if orient_match else None
    energy_cert = detect_energy_cert(description) or detect_energy_cert(html)
    state_flags = detect_state_flags(title + " " + description)

    return Property(
        source="idealista_playwright",
        url=url,
        title=title[:200],
        price=price,
        municipio=municipio or "",
        barrio=barrio,
        rooms=int(rooms) if rooms else None,
        bathrooms=int(bathrooms) if bathrooms else None,
        area_m2=float(area) if area else None,
        has_garage=has_garage,
        has_pool=has_pool,
        has_elevator=has_elevator,
        has_terrace=has_terrace,
        is_exterior=is_exterior,
        orientation=orientation,
        is_new_build=is_new_build,
        energy_cert=energy_cert,
        state_flags=state_flags,
        description=description[:800],
        raw={"days_on_market_hint": _days_on_market(html)},
    )
