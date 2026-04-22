from __future__ import annotations

from typing import Iterable

from .models import Property


def _zone_matches(prop: Property, zones: list[dict]) -> bool:
    for z in zones:
        if z["municipio"].lower() in (prop.municipio or "").lower():
            if not z.get("barrio"):
                return True
            if prop.barrio and z["barrio"].lower() in prop.barrio.lower():
                return True
    return False


def passes_hard_filters(prop: Property, criteria: dict, zones: dict) -> tuple[bool, str]:
    c = criteria

    if prop.price < c["price_min"] or prop.price > c["price_max"]:
        return False, f"precio fuera de rango ({prop.price:.0f})"

    if prop.rooms is not None and prop.rooms < c["rooms_min"]:
        return False, f"habitaciones < {c['rooms_min']}"

    if prop.area_m2 is not None and prop.area_m2 < c["area_min_m2"]:
        return False, f"superficie < {c['area_min_m2']} m²"

    must = set(c.get("must_have", []))
    if "garaje" in must and not prop.has_garage:
        return False, "sin garaje"
    if "piscina" in must and not prop.has_pool:
        return False, "sin piscina"
    if "ascensor" in must and not prop.has_elevator:
        return False, "sin ascensor"

    excluded_flags = set(c.get("exclude_states", []))
    if excluded_flags & set(prop.state_flags):
        bad = ", ".join(excluded_flags & set(prop.state_flags))
        return False, f"estado excluido: {bad}"

    if _zone_matches(prop, zones.get("excluded", [])):
        return False, "zona excluida"

    if zones.get("priority_1") or zones.get("priority_2"):
        in_p1 = _zone_matches(prop, zones.get("priority_1", []))
        in_p2 = _zone_matches(prop, zones.get("priority_2", []))
        if not (in_p1 or in_p2):
            return False, f"fuera de zonas objetivo ({prop.municipio}/{prop.barrio})"

    return True, "ok"


def filter_all(properties: Iterable[Property], criteria: dict, zones: dict) -> tuple[list[Property], list[tuple[Property, str]]]:
    kept: list[Property] = []
    dropped: list[tuple[Property, str]] = []
    for p in properties:
        ok, reason = passes_hard_filters(p, criteria, zones)
        if ok:
            kept.append(p)
        else:
            dropped.append((p, reason))
    return kept, dropped
