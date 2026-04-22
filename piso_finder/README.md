# piso_finder

Buscador automatizado de viviendas en Málaga y Costa del Sol, diseñado para el
perfil descrito en `../PLAN_COMPRA_VIVIENDA.md`:

- Presupuesto 200.000 € – 250.000 €
- Mínimo 2 habitaciones, garaje y piscina
- Preferente obra nueva o reciente
- Solo viviendas disponibles (excluye ocupadas, subastas, alquiladas, conflictos VUT)
- Financiación vía Programa Garantía Vivienda Andalucía (Ibercaja / Unicaja / Cajasur)

## Instalación

```bash
cd piso_finder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Algunas fuentes usan Playwright para sortear JavaScript pesado. Si quieres usar
esos scrapers, instala además los navegadores:

```bash
python -m playwright install chromium
```

## Uso

```bash
python -m piso_finder.cli --config config.yaml --output data/results.csv
```

Opciones:

- `--config` ruta al YAML de criterios (por defecto `config.yaml`).
- `--output` ruta del CSV de salida (por defecto `data/results.csv`).
- `--json` también volcar JSON completo (por defecto `data/results.json`).
- `--only` limitar a un scraper concreto: `idealista`, `fotocasa`, `pisos_com`, `habitaclia`.
- `--max-per-source` máximo de anuncios por fuente.
- `--dry-run` no hace red, usa fixtures de prueba (útil para depurar filtros).

## Qué hace

1. Lanza los scrapers listados en el config contra las zonas definidas.
2. Normaliza cada anuncio a un `Property` común (precio, m², habitaciones, extras).
3. Aplica filtros duros (precio, hab, garaje, piscina, disponibilidad).
4. Puntúa cada resultado (`scorer.py`): zona prioridad 1/2, €/m², obra nueva, etc.
5. Ordena de mejor a peor y escribe CSV + JSON.

## Ética y límites

- Los portales inmobiliarios prohíben scraping masivo en sus ToS. Usa este
  programa con **delays prudentes** (ya configurados) y **uso personal**.
- **Idealista tiene API oficial** (OAuth2, solicitar en developers.idealista.com).
  Si tienes credenciales, configúralas en `.env` y `idealista.py` las usa
  preferentemente frente al scraping web.
- Respeta `robots.txt` de cada sitio. El scraper lo comprueba al arrancar.
- Si una fuente empieza a bloquear, bajar la frecuencia y aumentar `delay_seconds`.

## Extender

Para añadir un portal nuevo, crea un módulo en `src/piso_finder/scrapers/`
que herede de `BaseScraper` e implementa `search(criteria)`. Regístralo en
`scrapers/__init__.py`.

## Estructura

```
piso_finder/
├── README.md
├── requirements.txt
├── config.yaml
├── data/
│   └── results.csv
└── src/piso_finder/
    ├── __init__.py
    ├── cli.py
    ├── models.py
    ├── filters.py
    ├── scorer.py
    ├── normalize.py
    └── scrapers/
        ├── __init__.py
        ├── base.py
        ├── idealista.py
        ├── fotocasa.py
        ├── pisos_com.py
        └── habitaclia.py
```
