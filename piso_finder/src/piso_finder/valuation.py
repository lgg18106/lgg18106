"""Módulo de valoración: compara precio de anuncio con benchmarks reales
(Tinsa, Notariado, Idealista histórico, Valor de Referencia del Catastro),
estima tasación, calcula ITP/gastos con base fiscal correcta y cuota de
hipoteca en escenario Programa Garantía Vivienda Andalucía.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import yaml

from .models import Property


@dataclass
class Benchmarks:
    tinsa_eur_m2: float
    notariado_eur_m2: float
    idealista_eur_m2: float
    price_change_12m: float
    avg_days_on_market: int
    commission_embedded: float


@dataclass
class Valuation:
    # Identificación
    title: str
    url: str
    municipio: str
    barrio: Optional[str]

    # Precio y superficie
    price: float
    area_m2: Optional[float]
    price_per_m2: Optional[float]
    is_new_build: bool
    days_on_market: Optional[int]
    valor_referencia_catastral: Optional[float]

    # Benchmarks
    tinsa_eur_m2: float
    notariado_eur_m2: float
    idealista_eur_m2: float

    # Gaps (%, decimal)
    gap_vs_tinsa: Optional[float]
    gap_vs_notariado: Optional[float]
    gap_vs_idealista: Optional[float]
    gap_vs_catastro: Optional[float]

    # Oferta recomendada
    oferta_min: float
    oferta_media: float
    oferta_max: float
    oferta_sugerida: float
    discount_pct: float
    discount_reasons: list[str]

    # Tasación estimada
    tasacion_min: float
    tasacion_max: float
    tasacion_central: float

    # Gastos e impuestos
    base_fiscal: float
    itp: float
    iva: float
    ajd: float
    notaria_registro_gestoria: float
    tasacion_coste: float
    gastos_totales: float

    # Hipoteca (Programa Garantía Vivienda Andalucía, 100 % sobre menor precio/tasación)
    hipoteca_capital: float
    hipoteca_cuota_mensual: float
    hipoteca_esfuerzo_pct: float
    efectivo_necesario: float

    # Veredicto
    veredicto: str
    semaforo: str   # verde / amarillo / rojo
    notas: list[str]


# ---------------------------------------------------------------------------
# Carga de benchmarks
# ---------------------------------------------------------------------------

def load_benchmarks(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_zone_benchmarks(benchmarks_cfg: dict, municipio: str, barrio: Optional[str]) -> Benchmarks:
    key = f"{municipio}/{barrio}" if barrio else municipio
    data = benchmarks_cfg.get("zones", {}).get(key)
    if not data:
        data = benchmarks_cfg.get("default")
    return Benchmarks(**data)


# ---------------------------------------------------------------------------
# Cálculo de oferta recomendada
# ---------------------------------------------------------------------------

def compute_discount(
    prop: Property,
    benchmarks: Benchmarks,
    discount_rules: dict,
    days_on_market: Optional[int],
    context: Optional[dict] = None,
) -> tuple[float, list[str]]:
    """Devuelve (pct, motivos). pct = fracción a rebajar sobre precio anuncio."""
    context = context or {}
    reasons: list[str] = []
    discount = 0.0

    if prop.is_new_build:
        discount = max(discount, discount_rules.get("obra_nueva", 0.02))
        reasons.append("obra nueva: promotoras bajan poco")
    else:
        d = days_on_market if days_on_market is not None else benchmarks.avg_days_on_market
        if d < 30:
            discount = max(discount, discount_rules.get("segunda_mano_menos_30_dias", 0.04))
            reasons.append(f"{d} días en portal: poco margen")
        elif d < 90:
            discount = max(discount, discount_rules.get("segunda_mano_30_90_dias", 0.06))
            reasons.append(f"{d} días en portal: margen moderado")
        elif d < 180:
            discount = max(discount, discount_rules.get("segunda_mano_90_180_dias", 0.09))
            reasons.append(f"{d} días en portal: vendedor empezando a ceder")
        else:
            discount = max(discount, discount_rules.get("segunda_mano_mas_180_dias", 0.12))
            reasons.append(f"{d} días en portal: vendedor muy motivado")

    if context.get("anuncio_con_bajada_visible"):
        discount += discount_rules.get("anuncio_con_bajada_visible", 0.05)
        reasons.append("anuncio ya con bajada de precio visible")
    if context.get("herencia_multiples_herederos"):
        discount = max(discount, discount_rules.get("herencia_multiples_herederos", 0.12))
        reasons.append("herencia con varios herederos motivados")
    if context.get("particular_sin_agencia"):
        discount = max(discount, discount_rules.get("particular_sin_agencia", 0.12))
        reasons.append("particular sin agencia")
    if context.get("agencia_exclusiva_grande"):
        discount = max(discount, discount_rules.get("agencia_exclusiva_grande", 0.06))
        reasons.append("agencia con exclusiva (margen menor)")

    return discount, reasons


# ---------------------------------------------------------------------------
# Tasación bancaria estimada
# ---------------------------------------------------------------------------

def estimate_appraisal(prop: Property, benchmarks: Benchmarks) -> tuple[float, float, float]:
    """Tasación suele estar en el tramo Notariado → Idealista.
    Devuelve (min, central, max).
    """
    if not prop.area_m2:
        return prop.price, prop.price, prop.price
    base_central = (benchmarks.notariado_eur_m2 + benchmarks.idealista_eur_m2) / 2
    low = benchmarks.notariado_eur_m2 * prop.area_m2
    mid = base_central * prop.area_m2
    high = benchmarks.idealista_eur_m2 * prop.area_m2
    return round(low, 0), round(mid, 0), round(high, 0)


# ---------------------------------------------------------------------------
# Gastos e impuestos
# ---------------------------------------------------------------------------

def compute_taxes_and_fees(
    prop: Property,
    base_fiscal: float,
    defaults: dict,
) -> dict:
    if prop.is_new_build:
        iva = base_fiscal * defaults["iva_rate_obra_nueva"]
        ajd = base_fiscal * defaults["ajd_rate_obra_nueva"]
        itp = 0.0
    else:
        itp = base_fiscal * defaults["itp_rate"]
        iva = ajd = 0.0
    notaria_etc = defaults["notaria_registro_gestoria"]
    tasacion = defaults["tasacion"]
    total = itp + iva + ajd + notaria_etc + tasacion
    return {
        "itp": round(itp, 0),
        "iva": round(iva, 0),
        "ajd": round(ajd, 0),
        "notaria_registro_gestoria": notaria_etc,
        "tasacion_coste": tasacion,
        "total": round(total, 0),
    }


# ---------------------------------------------------------------------------
# Hipoteca (Programa Garantía Vivienda Andalucía)
# ---------------------------------------------------------------------------

def monthly_payment(capital: float, tin_anual: float, plazo_anios: int) -> float:
    i = tin_anual / 12
    n = plazo_anios * 12
    if i == 0:
        return capital / n
    return capital * i / (1 - (1 + i) ** (-n))


def compute_mortgage(
    prop: Property,
    tasacion_central: float,
    mortgage_cfg: dict,
) -> dict:
    # Garantía Vivienda Andalucía: 100 % sobre el menor (precio, tasación).
    base_prestamo = min(prop.price, tasacion_central)
    cuota = monthly_payment(base_prestamo, mortgage_cfg["tin_fijo"], mortgage_cfg["plazo_anios"])
    neto = mortgage_cfg["neto_mensual"]
    esfuerzo = cuota / neto if neto else 0
    return {
        "capital": round(base_prestamo, 0),
        "cuota_mensual": round(cuota, 0),
        "esfuerzo_pct": round(esfuerzo, 3),
    }


# ---------------------------------------------------------------------------
# Veredicto
# ---------------------------------------------------------------------------

def build_verdict(
    prop: Property,
    gap_vs_notariado: Optional[float],
    gap_vs_idealista: Optional[float],
    gap_vs_catastro: Optional[float],
    esfuerzo_pct: float,
    days_on_market: Optional[int],
    cuota_max_pct: float,
) -> tuple[str, str, list[str]]:
    notas: list[str] = []
    semaforos: list[str] = []

    # Precio vs Idealista (techo típico del mercado)
    if gap_vs_idealista is None:
        semaforos.append("amarillo")
    elif gap_vs_idealista > 0.15:
        semaforos.append("rojo")
        notas.append(f"anuncio +{gap_vs_idealista*100:.0f}% sobre media Idealista — claramente inflado")
    elif gap_vs_idealista > 0.05:
        semaforos.append("amarillo")
        notas.append(f"+{gap_vs_idealista*100:.0f}% sobre Idealista — margen para negociar")
    else:
        semaforos.append("verde")
        notas.append(f"{gap_vs_idealista*100:+.0f}% vs Idealista — precio bien posicionado")

    # vs Notariado (piso de transacciones reales)
    if gap_vs_notariado is not None:
        if gap_vs_notariado > 0.30:
            semaforos.append("rojo")
            notas.append(f"+{gap_vs_notariado*100:.0f}% sobre Notariado — muy por encima de cierres reales")
        elif gap_vs_notariado > 0.15:
            semaforos.append("amarillo")
        else:
            semaforos.append("verde")

    # vs Catastro
    if gap_vs_catastro is not None:
        if gap_vs_catastro > 0.25:
            semaforos.append("amarillo")
            notas.append(f"+{gap_vs_catastro*100:.0f}% vs Valor de Referencia Catastro — margen claro de rebaja")
        elif gap_vs_catastro < -0.05:
            notas.append("por debajo de Valor de Referencia — Hacienda calcula ITP sobre Catastro, no sobre precio")

    # Esfuerzo hipotecario
    if esfuerzo_pct > cuota_max_pct:
        semaforos.append("rojo")
        notas.append(f"esfuerzo {esfuerzo_pct*100:.0f}% > {cuota_max_pct*100:.0f}% — cuota inviable")
    elif esfuerzo_pct > 0.32:
        semaforos.append("amarillo")
        notas.append(f"esfuerzo {esfuerzo_pct*100:.0f}% — al límite")
    else:
        semaforos.append("verde")

    # Días en portal
    if days_on_market is not None and days_on_market > 180 and not prop.is_new_build:
        notas.append(f"{days_on_market} días publicado — vendedor probablemente motivado a cerrar")

    # Veredicto global: rojo si hay algún rojo; amarillo si hay amarillos; verde si todo verde
    if "rojo" in semaforos:
        verdict = "rojo"
        text = "DESCARTAR o RENEGOCIAR fuerte: precio y/o cuota fuera de parámetros."
    elif "amarillo" in semaforos:
        verdict = "amarillo"
        text = "CANDIDATO con peros: negociable, hay que trabajar la oferta."
    else:
        verdict = "verde"
        text = "OPERACIÓN SANA: precio alineado con mercado y cuota asumible."

    return text, verdict, notas


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def analyze(
    prop: Property,
    benchmarks_cfg: dict,
    valor_referencia: Optional[float] = None,
    days_on_market: Optional[int] = None,
    context: Optional[dict] = None,
) -> Valuation:
    bm = get_zone_benchmarks(benchmarks_cfg, prop.municipio, prop.barrio)
    defaults = benchmarks_cfg.get("defaults", {})
    mortgage_cfg = defaults.get("mortgage", {})
    discount_rules = benchmarks_cfg.get("discount_rules", {})

    # Gaps
    ppm2 = prop.price_per_m2
    def _gap(bench):
        if ppm2 is None or bench == 0:
            return None
        return (ppm2 - bench) / bench

    gap_tinsa = _gap(bm.tinsa_eur_m2)
    gap_notariado = _gap(bm.notariado_eur_m2)
    gap_idealista = _gap(bm.idealista_eur_m2)
    gap_catastro = None
    if valor_referencia:
        gap_catastro = (prop.price - valor_referencia) / valor_referencia

    # Oferta recomendada
    discount_pct, reasons = compute_discount(prop, bm, discount_rules, days_on_market, context)
    oferta_sugerida = prop.price * (1 - discount_pct)
    oferta_media = prop.price * (1 - max(discount_pct - 0.02, 0.0))
    oferta_min = prop.price * (1 - min(discount_pct + 0.04, 0.20))
    oferta_max = prop.price

    # Tasación
    t_low, t_mid, t_high = estimate_appraisal(prop, bm)

    # Base fiscal (mayor entre precio y Valor de Referencia)
    base_fiscal = prop.price
    if valor_referencia and valor_referencia > prop.price:
        base_fiscal = valor_referencia
    fees = compute_taxes_and_fees(prop, base_fiscal, defaults)

    # Hipoteca
    mortgage = compute_mortgage(prop, t_mid, mortgage_cfg)
    efectivo = fees["total"] + max(prop.price - mortgage["capital"], 0)

    # Veredicto
    verdict_text, semaforo, notas = build_verdict(
        prop,
        gap_notariado,
        gap_idealista,
        gap_catastro,
        mortgage["esfuerzo_pct"],
        days_on_market,
        mortgage_cfg.get("cuota_max_pct", 0.35),
    )

    return Valuation(
        title=prop.title,
        url=prop.url,
        municipio=prop.municipio,
        barrio=prop.barrio,
        price=prop.price,
        area_m2=prop.area_m2,
        price_per_m2=ppm2,
        is_new_build=prop.is_new_build,
        days_on_market=days_on_market,
        valor_referencia_catastral=valor_referencia,
        tinsa_eur_m2=bm.tinsa_eur_m2,
        notariado_eur_m2=bm.notariado_eur_m2,
        idealista_eur_m2=bm.idealista_eur_m2,
        gap_vs_tinsa=gap_tinsa,
        gap_vs_notariado=gap_notariado,
        gap_vs_idealista=gap_idealista,
        gap_vs_catastro=gap_catastro,
        oferta_min=round(oferta_min, 0),
        oferta_media=round(oferta_media, 0),
        oferta_max=round(oferta_max, 0),
        oferta_sugerida=round(oferta_sugerida, 0),
        discount_pct=round(discount_pct, 3),
        discount_reasons=reasons,
        tasacion_min=t_low,
        tasacion_max=t_high,
        tasacion_central=t_mid,
        base_fiscal=base_fiscal,
        itp=fees["itp"],
        iva=fees["iva"],
        ajd=fees["ajd"],
        notaria_registro_gestoria=fees["notaria_registro_gestoria"],
        tasacion_coste=fees["tasacion_coste"],
        gastos_totales=fees["total"],
        hipoteca_capital=mortgage["capital"],
        hipoteca_cuota_mensual=mortgage["cuota_mensual"],
        hipoteca_esfuerzo_pct=mortgage["esfuerzo_pct"],
        efectivo_necesario=round(efectivo, 0),
        veredicto=verdict_text,
        semaforo=semaforo,
        notas=notas,
    )


def valuation_to_dict(v: Valuation) -> dict:
    return asdict(v)
