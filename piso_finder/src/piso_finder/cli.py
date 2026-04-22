from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from .filters import filter_all
from .models import Property
from .scorer import apply_scores
from .scrapers import build_scraper


console = Console()


def _load_fixtures() -> list[Property]:
    return [
        Property(
            source="fixture",
            url="https://example.com/a",
            title="Ático Playamar 2ª línea reformado",
            price=238000,
            municipio="Torremolinos",
            barrio="Playamar",
            rooms=2,
            bathrooms=2,
            area_m2=85,
            has_garage=True,
            has_pool=True,
            has_elevator=True,
            has_terrace=True,
            is_exterior=True,
            orientation="sur",
            is_new_build=False,
            energy_cert="C",
            description="Piso reformado con piscina y garaje, a 5 min de la playa.",
        ),
        Property(
            source="fixture",
            url="https://example.com/b",
            title="Obra nueva Los Álamos 2 dorm",
            price=225000,
            municipio="Torremolinos",
            barrio="Los Álamos",
            rooms=2,
            area_m2=78,
            has_garage=True,
            has_pool=True,
            has_elevator=True,
            is_new_build=True,
            energy_cert="A",
            description="Promoción a estrenar con piscina comunitaria y garaje.",
        ),
        Property(
            source="fixture",
            url="https://example.com/c",
            title="Piso en Las Lagunas con urbanización",
            price=210000,
            municipio="Mijas",
            barrio="Las Lagunas",
            rooms=3,
            area_m2=92,
            has_garage=True,
            has_pool=True,
            has_elevator=True,
            has_terrace=True,
            energy_cert="D",
            description="Urbanización con piscina, garaje y trastero.",
        ),
        Property(
            source="fixture",
            url="https://example.com/d",
            title="Piso Mijas Golf oportunidad",
            price=225000,
            municipio="Mijas",
            barrio="Mijas Golf",
            rooms=2,
            area_m2=70,
            has_garage=True,
            has_pool=True,
            has_elevator=False,
            description="Vistas al campo de golf.",
        ),
        Property(
            source="fixture",
            url="https://example.com/e",
            title="Piso ocupado en Fuengirola - descuento",
            price=215000,
            municipio="Fuengirola",
            barrio="Los Boliches",
            rooms=2,
            area_m2=75,
            has_garage=True,
            has_pool=True,
            has_elevator=True,
            description="Inmueble ocupado, venta con ocupantes.",
            state_flags=["ocupado"],
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Buscador de viviendas Málaga / Costa del Sol")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", default=None)
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--only", default=None, help="Limitar a un scraper")
    parser.add_argument("--max-per-source", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true", help="Usa fixtures en lugar de red")
    args = parser.parse_args(argv)

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        console.print(f"[red]No se encuentra el config: {cfg_path}[/red]")
        return 2
    cfg = yaml.safe_load(cfg_path.read_text())

    criteria = cfg["criteria"]
    zones = cfg["zones"]
    scraper_cfgs = cfg.get("scrapers", {})
    weights = cfg.get("scoring", {}).get("weights", {})
    out_csv = args.output or cfg.get("output", {}).get("csv", "data/results.csv")
    out_json = args.json_path or cfg.get("output", {}).get("json", "data/results.json")

    all_props: list[Property] = []

    if args.dry_run:
        console.print("[yellow]Dry-run: cargando fixtures, sin red.[/yellow]")
        all_props = _load_fixtures()
    else:
        for name, scfg in scraper_cfgs.items():
            if args.only and args.only != name:
                continue
            if not scfg.get("enabled"):
                continue
            console.print(f"[cyan]→ {name}[/cyan]")
            try:
                scraper = build_scraper(name, scfg)
                count = 0
                for prop in scraper.search(criteria, zones):
                    all_props.append(prop)
                    count += 1
                    if count >= args.max_per_source:
                        break
                console.print(f"  [green]{count}[/green] anuncios capturados")
            except Exception as e:
                console.print(f"  [red]error: {e}[/red]")

    console.print(f"\n[bold]Total bruto: {len(all_props)}[/bold]")
    kept, dropped = filter_all(all_props, criteria, zones)
    console.print(f"[bold]Pasan filtros: {len(kept)} · descartados: {len(dropped)}[/bold]")

    kept = apply_scores(kept, zones, weights)

    os.makedirs(Path(out_csv).parent, exist_ok=True)
    if kept:
        fieldnames = list(kept[0].to_dict().keys())
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for p in kept:
                writer.writerow(p.to_dict())
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in kept], f, ensure_ascii=False, indent=2)

    _print_top(kept, n=15)

    drop_path = Path(out_csv).with_suffix(".descartados.csv")
    if dropped:
        with open(drop_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["url", "motivo", "titulo", "precio"])
            for p, reason in dropped:
                writer.writerow([p.url, reason, p.title, p.price])

    console.print(f"\nCSV: [bold]{out_csv}[/bold]  ·  JSON: [bold]{out_json}[/bold]")
    if dropped:
        console.print(f"Descartados: [dim]{drop_path}[/dim]")
    return 0


def _print_top(props: list[Property], n: int = 15) -> None:
    if not props:
        return
    t = Table(title=f"Top {min(n, len(props))}")
    t.add_column("#", justify="right")
    t.add_column("Score", justify="right")
    t.add_column("Precio", justify="right")
    t.add_column("€/m²", justify="right")
    t.add_column("Municipio")
    t.add_column("Barrio")
    t.add_column("m²", justify="right")
    t.add_column("Hab", justify="right")
    t.add_column("Fuente")
    t.add_column("Título", overflow="fold")
    for i, p in enumerate(props[:n], 1):
        t.add_row(
            str(i),
            f"{p.score:.1f}",
            f"{p.price:,.0f}",
            f"{p.price_per_m2:.0f}" if p.price_per_m2 else "-",
            p.municipio,
            p.barrio or "-",
            f"{p.area_m2:.0f}" if p.area_m2 else "-",
            str(p.rooms or "-"),
            p.source,
            p.title[:60],
        )
    console.print(t)


if __name__ == "__main__":
    sys.exit(main())
