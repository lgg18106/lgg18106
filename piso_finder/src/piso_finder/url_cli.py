"""CLI one-shot: URL Idealista → fetch con Playwright → análisis completo."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console

from .analyze_cli import _print_valuation
from .models import Property
from .scrapers.idealista_playwright import fetch_property
from .valuation import analyze, load_benchmarks, valuation_to_dict


console = Console()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="URL Idealista → análisis completo")
    p.add_argument("url", help="URL del anuncio (ej: https://www.idealista.com/inmueble/111044335/)")
    p.add_argument("--benchmarks", default="data/benchmarks.yaml")
    p.add_argument("--valor-referencia", type=float, default=None)
    p.add_argument("--days-on-market", type=int, default=None)
    p.add_argument("--context", default=None)
    p.add_argument("--show-browser", action="store_true",
                   help="Lanza navegador visible (útil si Idealista pide captcha)")
    p.add_argument("--state-file", default=None,
                   help="Ruta al storage_state (por defecto ~/.piso_finder/idealista_state.json)")
    p.add_argument("--json-out", default=None)
    args = p.parse_args(argv)

    console.print(f"[cyan]→ fetching[/cyan] {args.url}")
    dump = None
    if args.json_out:
        dump = args.json_out.replace(".json", ".html")
    try:
        prop: Property = fetch_property(
            args.url,
            headless=not args.show_browser,
            dump_html=dump,
            state_file=args.state_file,
        )
    except Exception as e:
        msg = f"fetch falló: {e}"
        console.print(f"[red]{msg}[/red]")
        console.print(
            "[yellow]Si Idealista bloquea, prueba --show-browser la primera vez para "
            "pasar el captcha, o pega los datos a mano en un JSON y usa piso_finder-analyze.[/yellow]"
        )
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps({"error": msg, "url": args.url}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return 2

    if not prop.price:
        console.print("[red]No se pudo extraer el precio. Revisa la URL o usa --show-browser.[/red]")
        return 3

    console.print(
        f"[green]✓[/green] {prop.title} · "
        f"{prop.price:,.0f} € · {prop.area_m2} m² · "
        f"{prop.municipio}/{prop.barrio}"
    )

    days = args.days_on_market
    if days is None:
        days = prop.raw.get("days_on_market_hint") if prop.raw else None

    bench = load_benchmarks(args.benchmarks)
    ctx = json.loads(args.context) if args.context else None

    val = analyze(
        prop,
        bench,
        valor_referencia=args.valor_referencia,
        days_on_market=days,
        context=ctx,
    )

    _print_valuation(val)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"property": prop.to_dict(), "valuation": valuation_to_dict(val)},
                ensure_ascii=False,
                indent=2,
                default=list,
            ),
            encoding="utf-8",
        )
        console.print(f"\nJSON: [bold]{args.json_out}[/bold]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
