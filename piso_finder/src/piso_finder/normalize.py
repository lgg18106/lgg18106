from __future__ import annotations

import re
from typing import Optional


_STATE_KEYWORDS = {
    "ocupado": ["ocupad", "okupa"],
    "alquilado": ["alquilad", "con contrato de alquiler"],
    "con_inquilino": ["con inquilino", "con inquilinos"],
    "subasta": ["subasta"],
    "adjudicacion": ["adjudicad"],
    "nuda_propiedad": ["nuda propiedad", "nuda propied"],
    "alquiler_con_opcion": ["alquiler con opción", "alquiler con opcion"],
    "vut_en_conflicto": ["licencia vut con conflicto", "conflicto vut"],
}


def detect_state_flags(text: str) -> list[str]:
    if not text:
        return []
    t = text.lower()
    flags: list[str] = []
    for flag, kws in _STATE_KEYWORDS.items():
        if any(kw in t for kw in kws):
            flags.append(flag)
    return flags


def parse_int_euro(s: str) -> Optional[float]:
    if not s:
        return None
    digits = re.sub(r"[^\d]", "", s)
    return float(digits) if digits else None


def parse_area_m2(s: str) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m", s.lower())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_rooms(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"(\d+)\s*(hab|dorm)", s.lower())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def has_keyword(text: str, *kws: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in kws)


def detect_energy_cert(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"certificaci[oó]n\s+energ[eé]tica\s*[:\-]?\s*([A-G])", text, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"calificaci[oó]n\s+energ[eé]tica\s*[:\-]?\s*([A-G])", text, re.I)
    if m:
        return m.group(1).upper()
    return None
