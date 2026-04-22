from __future__ import annotations

from .models import Property


PRICE_PER_M2_BENCHMARKS = {
    "Torremolinos": 3400,
    "Mijas": 3000,
    "Fuengirola": 3700,
    "Rincón de la Victoria": 3400,
    "Benalmádena": 3300,
}


def _zone_score(prop: Property, zones: dict) -> float:
    for z in zones.get("priority_1", []):
        if z["municipio"].lower() in (prop.municipio or "").lower() and (
            not z.get("barrio") or (prop.barrio and z["barrio"].lower() in prop.barrio.lower())
        ):
            return 1.0
    for z in zones.get("priority_2", []):
        if z["municipio"].lower() in (prop.municipio or "").lower() and (
            not z.get("barrio") or (prop.barrio and z["barrio"].lower() in prop.barrio.lower())
        ):
            return 0.6
    return 0.0


def _price_per_m2_score(prop: Property) -> float:
    if prop.price_per_m2 is None:
        return 0.3
    benchmark = PRICE_PER_M2_BENCHMARKS.get(prop.municipio, 3300)
    ratio = prop.price_per_m2 / benchmark
    if ratio <= 0.80:
        return 1.0
    if ratio <= 0.90:
        return 0.85
    if ratio <= 1.00:
        return 0.65
    if ratio <= 1.10:
        return 0.40
    return 0.15


def _cert_score(prop: Property) -> float:
    if not prop.energy_cert:
        return 0.3
    c = prop.energy_cert.upper()[0]
    return {"A": 1.0, "B": 0.85, "C": 0.6, "D": 0.4, "E": 0.25}.get(c, 0.15)


def score(prop: Property, zones: dict, weights: dict) -> float:
    z = _zone_score(prop, zones) * weights.get("zone_priority", 0)
    p = _price_per_m2_score(prop) * weights.get("price_per_m2", 0)
    n = (1.0 if prop.is_new_build else 0.3) * weights.get("obra_nueva", 0)
    e = _cert_score(prop) * weights.get("certificacion_energetica", 0)
    g = (1.0 if prop.has_garage else 0.0) * weights.get("garaje", 0)
    po = (1.0 if prop.has_pool else 0.0) * weights.get("piscina", 0)
    t = (1.0 if (prop.has_terrace or prop.is_exterior) else 0.0) * weights.get("exterior_terraza", 0)
    a = (1.0 if prop.has_elevator else 0.0) * weights.get("ascensor", 0)
    total = z + p + n + e + g + po + t + a
    return round(total, 2)


def apply_scores(properties: list[Property], zones: dict, weights: dict) -> list[Property]:
    for p in properties:
        p.score = score(p, zones, weights)
    properties.sort(key=lambda x: x.score, reverse=True)
    return properties
