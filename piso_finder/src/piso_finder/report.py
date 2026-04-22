from __future__ import annotations

from pathlib import Path

from .models import Property


_CSS = """
body { font: 14px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; margin: 2rem; color: #222; }
h1 { margin: 0 0 .25rem 0; }
.sub { color: #666; margin-bottom: 1.5rem; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid #eee; padding: .55rem .5rem; text-align: left; vertical-align: top; }
th { background: #f7f7f9; font-weight: 600; }
tr:hover { background: #fafbff; }
.score { font-weight: 700; color: #0a6; }
.badge { display: inline-block; padding: .1rem .5rem; border-radius: 999px; background: #eef; color: #225; font-size: .75rem; margin-right: .25rem; }
.badge.obra { background: #e6f7ea; color: #1a7a3a; }
.badge.certA { background: #e6f4ff; color: #0a58b8; }
.price { font-weight: 600; }
a { color: #0645ad; text-decoration: none; }
a:hover { text-decoration: underline; }
"""


def render_html(props: list[Property], top_n: int, out_path: str) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, p in enumerate(props[:top_n], 1):
        badges = []
        if p.is_new_build:
            badges.append('<span class="badge obra">obra nueva</span>')
        if p.energy_cert in {"A", "B"}:
            badges.append(f'<span class="badge certA">cert. {p.energy_cert}</span>')
        if p.has_pool:
            badges.append('<span class="badge">piscina</span>')
        if p.has_garage:
            badges.append('<span class="badge">garaje</span>')
        if p.has_terrace:
            badges.append('<span class="badge">terraza</span>')
        if p.orientation:
            badges.append(f'<span class="badge">{p.orientation}</span>')

        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td class='score'>{p.score:.1f}</td>"
            f"<td class='price'>{p.price:,.0f} €</td>"
            f"<td>{p.price_per_m2:,.0f} €/m²</td>" if p.price_per_m2 else "<td>-</td>"
        )

    # cleaner rebuild
    rows = []
    for i, p in enumerate(props[:top_n], 1):
        badges = []
        if p.is_new_build:
            badges.append('<span class="badge obra">obra nueva</span>')
        if p.energy_cert in {"A", "B"}:
            badges.append(f'<span class="badge certA">cert. {p.energy_cert}</span>')
        if p.has_terrace:
            badges.append('<span class="badge">terraza</span>')
        if p.orientation:
            badges.append(f'<span class="badge">{p.orientation}</span>')
        badges_html = " ".join(badges)

        ppm2 = f"{p.price_per_m2:,.0f} €/m²" if p.price_per_m2 else "-"
        area = f"{p.area_m2:.0f} m²" if p.area_m2 else "-"
        rooms = str(p.rooms) if p.rooms is not None else "-"
        title_link = f"<a href='{p.url}' target='_blank' rel='noopener'>{p.title}</a>"
        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td class='score'>{p.score:.1f}</td>"
            f"<td class='price'>{p.price:,.0f} €</td>"
            f"<td>{ppm2}</td>"
            f"<td>{p.municipio}<br><small>{p.barrio or ''}</small></td>"
            f"<td>{area}</td>"
            f"<td>{rooms}</td>"
            f"<td>{badges_html}</td>"
            f"<td>{title_link}<br><small>{p.source}</small></td>"
            "</tr>"
        )

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>piso_finder — Top {top_n}</title>
<style>{_CSS}</style></head><body>
<h1>piso_finder — Top {min(top_n, len(props))}</h1>
<div class="sub">Resultados ordenados por score. {len(props)} anuncios superan los filtros.</div>
<table>
<thead><tr><th>#</th><th>Score</th><th>Precio</th><th>€/m²</th><th>Zona</th><th>Sup.</th><th>Hab</th><th>Extras</th><th>Anuncio</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
</body></html>"""
    path.write_text(html, encoding="utf-8")
