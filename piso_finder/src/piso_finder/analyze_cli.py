"""CLI para analizar un anuncio concreto contra benchmarks de mercado."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Property
from .scrapers.local_file import LocalFileScraper
from .valuation import analyze, load_benchmarks, valuation_to_dict


console = Console()

SEMAFORO_STYLE = {
    "verde": "bold green",
    "amarillo": "bold yellow",
    "rojo": "bold red",
}


def _load_property(input_path: Path) -> Property:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        if len(data) != 1:
            console.print(f"[red]El archivo contiene {len(data)} anuncios. Usa --index N o un solo objeto.[/red]")
            sys.exit(2)
        data = data[0]
    scraper = LocalFileScraper({"paths": []})
    return scraper._row_to_property(data)


def _fmt_eur(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v:,.0f} €".replace(",", ".")


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v*100:+.1f}%"


def _print_valuation(val) -> None:
    # Encabezado
    console.print()
    console.print(Panel.fit(
        f"[bold]{val.title}[/bold]\n[dim]{val.url}[/dim]\n"
        f"{val.municipio} · {val.barrio or '-'}   "
        f"[cyan]{_fmt_eur(val.price)}[/cyan]   "
        f"{val.area_m2:.0f} m²   "
        f"[cyan]{val.price_per_m2:,.0f} €/m²[/cyan]"
        f"{' · obra nueva' if val.is_new_build else ''}",
        border_style="cyan",
    ))

    # Benchmarks
    t = Table(title="Precio anuncio vs benchmarks de zona", show_header=True, header_style="bold")
    t.add_column("Fuente")
    t.add_column("€/m² zona", justify="right")
    t.add_column("Gap anuncio", justify="right")
    t.add_column("Lectura")
    def row(name, bench, gap, explainer):
        if gap is None:
            color = "white"
        elif gap > 0.15:
            color = "red"
        elif gap > 0.05:
            color = "yellow"
        else:
            color = "green"
        t.add_row(name, f"{bench:,.0f}", f"[{color}]{_fmt_pct(gap)}[/{color}]", explainer)

    row("Tinsa IMIE",        val.tinsa_eur_m2,     val.gap_vs_tinsa,     "tasación real")
    row("Notariado (cierre)", val.notariado_eur_m2, val.gap_vs_notariado, "precio medio escriturado")
    row("Idealista (oferta)", val.idealista_eur_m2, val.gap_vs_idealista, "techo típico de anuncios")
    if val.valor_referencia_catastral:
        t.add_row(
            "Valor Referencia Catastro",
            f"{val.valor_referencia_catastral/val.area_m2:,.0f}" if val.area_m2 else "-",
            f"[{'red' if val.gap_vs_catastro and val.gap_vs_catastro>0.25 else 'yellow' if val.gap_vs_catastro and val.gap_vs_catastro>0.10 else 'green'}]{_fmt_pct(val.gap_vs_catastro)}[/]",
            "base fiscal mínima",
        )
    console.print(t)

    # Oferta recomendada
    t2 = Table(title="Rango de oferta recomendado", show_header=True, header_style="bold")
    t2.add_column("Escenario")
    t2.add_column("Precio", justify="right")
    t2.add_column("Descuento", justify="right")
    t2.add_row("Agresivo (mínimo)", _fmt_eur(val.oferta_min), f"-{(1 - val.oferta_min/val.price)*100:.1f}%")
    t2.add_row("[bold cyan]Oferta sugerida[/bold cyan]", f"[bold cyan]{_fmt_eur(val.oferta_sugerida)}[/bold cyan]", f"-{val.discount_pct*100:.1f}%")
    t2.add_row("Medio", _fmt_eur(val.oferta_media), f"-{(1 - val.oferta_media/val.price)*100:.1f}%")
    t2.add_row("Sin rebaja (máximo)", _fmt_eur(val.oferta_max), "0.0%")
    console.print(t2)
    for r in val.discount_reasons:
        console.print(f"  · {r}")

    # Tasación
    console.print()
    console.print(
        f"[bold]Tasación bancaria estimada:[/bold] "
        f"{_fmt_eur(val.tasacion_min)} – [cyan]{_fmt_eur(val.tasacion_central)}[/cyan] – {_fmt_eur(val.tasacion_max)}"
    )
    if val.tasacion_central < val.price:
        delta = val.price - val.tasacion_central
        console.print(f"  [yellow]Tasación central < precio por {_fmt_eur(delta)} → aportas tú esa diferencia o renegocias[/yellow]")

    # Gastos
    t3 = Table(title="Impuestos y gastos", show_header=True, header_style="bold")
    t3.add_column("Concepto")
    t3.add_column("Importe", justify="right")
    t3.add_row("Base fiscal (mayor de precio/Catastro)", _fmt_eur(val.base_fiscal))
    if val.itp:
        t3.add_row("ITP Andalucía 7 %", _fmt_eur(val.itp))
    if val.iva:
        t3.add_row("IVA 10 %", _fmt_eur(val.iva))
    if val.ajd:
        t3.add_row("AJD 1,2 %", _fmt_eur(val.ajd))
    t3.add_row("Notaría + Registro + gestoría", _fmt_eur(val.notaria_registro_gestoria))
    t3.add_row("Tasación", _fmt_eur(val.tasacion_coste))
    t3.add_row("[bold]Total gastos[/bold]", f"[bold]{_fmt_eur(val.gastos_totales)}[/bold]")
    console.print(t3)

    # Hipoteca
    esf_color = "red" if val.hipoteca_esfuerzo_pct > 0.35 else "yellow" if val.hipoteca_esfuerzo_pct > 0.32 else "green"
    t4 = Table(title="Hipoteca (Programa Garantía Vivienda Andalucía, 100 % menor precio/tasación)", header_style="bold")
    t4.add_column("Concepto")
    t4.add_column("Valor", justify="right")
    t4.add_row("Capital financiado", _fmt_eur(val.hipoteca_capital))
    t4.add_row("Cuota mensual estimada", f"[bold]{_fmt_eur(val.hipoteca_cuota_mensual)}[/bold]")
    t4.add_row("Esfuerzo sobre neto", f"[{esf_color}]{val.hipoteca_esfuerzo_pct*100:.0f}%[/{esf_color}]")
    t4.add_row("Efectivo necesario (gastos + diferencia)", _fmt_eur(val.efectivo_necesario))
    console.print(t4)

    # Veredicto
    color = SEMAFORO_STYLE.get(val.semaforo, "white")
    console.print()
    console.print(Panel(
        f"[{color}]{val.semaforo.upper()}[/{color}] — {val.veredicto}" +
        ("\n\n" + "\n".join(f"· {n}" for n in val.notas) if val.notas else ""),
        title="Veredicto",
        border_style=color.split()[-1],
    ))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Analizar un anuncio contra benchmarks reales de zona")
    p.add_argument("input", help="Ruta a JSON con un anuncio (o lista con uno)")
    p.add_argument("--benchmarks", default="data/benchmarks.yaml")
    p.add_argument("--valor-referencia", type=float, default=None,
                   help="Valor de referencia del Catastro (€) de ese inmueble concreto")
    p.add_argument("--days-on-market", type=int, default=None,
                   help="Días que lleva publicado el anuncio")
    p.add_argument("--context", default=None,
                   help="JSON inline con flags: herencia_multiples_herederos, particular_sin_agencia, etc.")
    p.add_argument("--json-out", default=None,
                   help="Exportar análisis a JSON")
    args = p.parse_args(argv)

    prop = _load_property(Path(args.input))
    bench = load_benchmarks(args.benchmarks)
    ctx = json.loads(args.context) if args.context else None

    val = analyze(
        prop,
        bench,
        valor_referencia=args.valor_referencia,
        days_on_market=args.days_on_market,
        context=ctx,
    )

    _print_valuation(val)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(valuation_to_dict(val), ensure_ascii=False, indent=2, default=list),
            encoding="utf-8",
        )
        console.print(f"\nJSON: [bold]{args.json_out}[/bold]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
