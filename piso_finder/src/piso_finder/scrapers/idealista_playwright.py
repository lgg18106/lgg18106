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


def _fetch_via_scrapingbee(url: str, timeout: int = 60) -> Optional[str]:
    """ScrapingBee (free tier 1000 req/mes) con IPs residenciales rotativas
    y render JS. Pasa DataDome en la mayoría de los casos.

    Requiere variable de entorno SCRAPINGBEE_KEY.
    Registro gratuito: https://app.scrapingbee.com/account/register
    """
    import os
    import requests
    key = os.getenv("SCRAPINGBEE_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": key,
                "url": url,
                "render_js": "true",
                "premium_proxy": "true",
                "country_code": "es",
                "wait": "3000",
            },
            timeout=timeout,
        )
        if r.status_code == 200 and len(r.text) > 2000:
            return r.text
    except Exception:
        return None
    return None


def _fetch_via_jina_reader(url: str, timeout: int = 45) -> Optional[str]:
    """r.jina.ai convierte cualquier URL a markdown, saltándose Cloudflare
    desde sus propios servidores. Gratis y sin API key. Devuelve markdown o None."""
    import requests
    try:
        r = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/markdown", "X-With-Generated-Alt": "true"},
            timeout=timeout,
        )
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        return None
    return None


def _parse_markdown(url: str, md: str) -> Property:
    """Extrae campos desde el markdown devuelto por r.jina.ai."""
    text = md
    title_m = re.search(r"^#\s*(.+)$", md, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else ""

    # Precio: primer "123.456 €" razonable
    price = None
    for m in re.finditer(r"(\d[\d\.\s]{4,})\s*€", md):
        val = parse_int_euro(m.group(1))
        if val and 20000 <= val <= 5_000_000:
            price = val
            break

    area = parse_area_m2(md)
    rooms = parse_rooms(md)

    # Municipio/barrio: buscar patrones tipo "Playamar, Torremolinos"
    municipio = ""
    barrio = None
    loc = re.search(
        r"\b(Playamar|Los Álamos|El Pinar|Las Lagunas|La Cala(?:\s+de\s+Mijas)?|Los Boliches|Torreblanca|Carvajal|Cotomar|Añoreta|Arroyo de la Miel|Benalmádena Costa|Carihuela|Torre del Mar|Mijas Golf|Mijas Pueblo|Playamar-El Pinillo)[^,\n]*,\s*([A-ZÁÉÍÓÚÑ][\wáéíóúñ\-\s]+)",
        md,
    )
    if loc:
        barrio = loc.group(1).strip()
        municipio = loc.group(2).strip()
    else:
        # fallback por palabra clave
        for mun in ["Torremolinos", "Mijas", "Fuengirola", "Benalmádena", "Rincón de la Victoria", "Málaga", "Vélez-Málaga"]:
            if mun in md:
                municipio = mun
                break

    description = md[:2000]

    return Property(
        source="jina_reader",
        url=url,
        title=title[:200] if title else "",
        price=price or 0.0,
        municipio=municipio,
        barrio=barrio,
        rooms=rooms,
        area_m2=area,
        has_garage=has_keyword(md, "garaje", "plaza de garaje", "parking"),
        has_pool=has_keyword(md, "piscina"),
        has_elevator=has_keyword(md, "ascensor"),
        has_terrace=has_keyword(md, "terraza", "balcón", "balcon"),
        is_exterior=has_keyword(md, "exterior"),
        is_new_build=has_keyword(md, "obra nueva", "a estrenar", "promoción"),
        energy_cert=detect_energy_cert(md),
        state_flags=detect_state_flags(md),
        description=description,
        raw={"fallback": "jina_reader"},
    )


def fetch_property(url: str, headless: bool = True, timeout_ms: int = 60000, dump_html: str | None = None) -> Property:
    """Descarga la página con Playwright y devuelve un Property normalizado.

    Aplica playwright-stealth si está instalado (mejor tasa de éxito con
    Cloudflare / DataDome). Si dump_html es una ruta, guarda el HTML final
    ahí para depuración.

    Requiere haber ejecutado previamente:
        pip install playwright playwright-stealth
        playwright install chromium
    """
    # Plan A: ScrapingBee (si hay API key) — IPs residenciales, pasa DataDome.
    html_from_sb = None
    try:
        html_from_sb = _fetch_via_scrapingbee(url)
        if html_from_sb:
            if dump_html:
                try:
                    with open(dump_html, "w", encoding="utf-8") as f:
                        f.write(html_from_sb)
                except Exception:
                    pass
            prop = _parse_html(url, html_from_sb)
            if prop.price and prop.municipio:
                return prop
    except Exception:
        pass

    # Plan B: r.jina.ai (gratis, pero los servers de jina también pueden
    # recibir la página de bloqueo DataDome).
    try:
        md = _fetch_via_jina_reader(url)
        if md:
            if dump_html and not html_from_sb:
                try:
                    with open(dump_html, "w", encoding="utf-8") as f:
                        f.write(md)
                except Exception:
                    pass
            prop = _parse_markdown(url, md)
            if prop.price and prop.municipio:
                return prop
    except Exception:
        pass

    # Plan B: Playwright (solo si lo anterior no dio precio/ubicación).
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Ni r.jina.ai ni Playwright pudieron obtener datos. "
            "Instala Playwright: pip install playwright playwright-stealth && playwright install chromium"
        ) from e

    try:
        from playwright_stealth import stealth_sync  # type: ignore
    except ImportError:
        stealth_sync = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
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
        if stealth_sync is not None:
            try:
                stealth_sync(page)
            except Exception:
                pass

        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        status = response.status if response else None
        if status and status >= 400:
            html = page.content()
            if dump_html:
                try:
                    with open(dump_html, "w", encoding="utf-8") as f:
                        f.write(html)
                except Exception:
                    pass
            browser.close()
            raise RuntimeError(f"HTTP {status} al cargar {url} (posible antibot).")

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

        page.wait_for_timeout(2500)

        # Detección básica de captcha / página de bloqueo
        html_lower = page.content().lower()
        if any(k in html_lower for k in [
            "cloudflare", "captcha", "verificamos que es usted una persona",
            "access denied", "just a moment", "request unsuccessful",
        ]) and "application/ld+json" not in html_lower:
            if dump_html:
                try:
                    with open(dump_html, "w", encoding="utf-8") as f:
                        f.write(page.content())
                except Exception:
                    pass
            browser.close()
            raise RuntimeError(
                f"Página de bloqueo/captcha detectada en {url}. Prueba --show-browser."
            )

        html = page.content()
        if dump_html:
            try:
                with open(dump_html, "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                pass
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
