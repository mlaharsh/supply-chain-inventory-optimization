# Deployment guide

This project is a batch analytics pipeline **and** a public portfolio dashboard. It is deployed in layers:

| Layer | Host | URL |
|---|---|---|
| Source code | GitHub | <https://github.com/mlaharsh/supply-chain-inventory-optimization> |
| Executive dashboard preview | GitHub Pages | <https://mlaharsh.github.io/supply-chain-inventory-optimization/> |
| Interactive dashboard | Streamlit Community Cloud | <https://supply-chain-inventory-optimization-2o6rasyypmbxh3tpxtpxni.streamlit.app/> |
| Pipeline tests + regenerated outputs | GitHub Actions | [CI workflow](https://github.com/mlaharsh/supply-chain-inventory-optimization/actions/workflows/ci.yml) |
| Interactive workbook | Tableau Public | Optional — workbook specification only |
| Production-style database | Managed PostgreSQL | Optional — not live-tested in this build |

The data is synthetic. The only generated files committed to Git are the ten CSV extracts under `outputs/tableau/`; they are the dashboard snapshot used by Streamlit. Everything else is reproducible with the pipeline.

---

## 1. GitHub Pages

Pages serves static HTML from `main` / `docs`.

- Entry point: `docs/index.html`
- Responsive dashboard wrapper: `docs/preview.html`
- Source dashboard: `docs/dashboard_preview.html`
- Screenshot: `docs/dashboard_preview.png`

The `docs/.nojekyll` marker disables Jekyll processing.

### First-time setup

1. Push `main`.
2. Open **Repository → Settings → Pages**.
3. Set **Source** to **Deploy from a branch**.
4. Select branch **main** and folder **/docs**.
5. Save. The first deployment takes about 1–2 minutes.

The site is then available at:

```text
https://mlaharsh.github.io/supply-chain-inventory-optimization/
```

### Verify

```bash
curl -I https://mlaharsh.github.io/supply-chain-inventory-optimization/
```

A `200` response confirms Pages is serving the landing page.

---

## 2. Streamlit Community Cloud

**Live app:** <https://supply-chain-inventory-optimization-2o6rasyypmbxh3tpxtpxni.streamlit.app/>

`app.py` is a four-page Streamlit dashboard:

1. **Executive Overview** — KPIs, ABC-XYZ heatmap, action queue, supplier performance, inventory trend.
2. **Reorder Queue** — risk filters, revenue exposure, inventory position vs ROP, decision table, open POs.
3. **Supplier Performance** — scorecard, promised vs actual lead time, variance distribution, exposure.
4. **SKU Drilldown** — monthly forecast, weekly demand, inventory vs retro ROP, policy levels, PO history.

### Deploy

1. Go to <https://share.streamlit.io>.
2. Sign in with GitHub.
3. Choose **Create app** / **New app**.
4. Select:
   - Repository: `mlaharsh/supply-chain-inventory-optimization`
   - Branch: `main`
   - Main file path: `app.py`
5. Click **Deploy**.

Streamlit installs `requirements.txt`, so `streamlit` and `plotly` are available. The app reads the committed snapshot from `outputs/tableau/`; no database or pipeline run is needed at startup.

The first sign-in requires email verification (Streamlit sends a one-time code). After that, the app deploys directly from `main` and redeploys on every push.

### Direct page links

The app reads the `page` query parameter, so each page is linkable:

```text
https://supply-chain-inventory-optimization-2o6rasyypmbxh3tpxtpxni.streamlit.app/?page=overview
https://supply-chain-inventory-optimization-2o6rasyypmbxh3tpxtpxni.streamlit.app/?page=queue
https://supply-chain-inventory-optimization-2o6rasyypmbxh3tpxtpxni.streamlit.app/?page=suppliers
https://supply-chain-inventory-optimization-2o6rasyypmbxh3tpxtpxni.streamlit.app/?page=sku
```

### Local run

```bash
python -m pip install -e ".[app,dev]"
streamlit run app.py
```

Open <http://localhost:8501>.

---

## 3. GitHub Actions

`.github/workflows/ci.yml` runs on every push and pull request:

```text
checkout → Python 3.11 → install → compile app.py → pytest
→ regenerate full pipeline → verify output contracts → upload artifacts
```

The workflow uploads the analytics tables, Tableau extracts, run summary, quality report, and executive summary as a build artifact retained for 30 days.

That means every push proves the project is reproducible even though generated outputs are not tracked in Git (except the dashboard snapshot).

---

## 4. Tableau Public (optional)

The repository ships a dashboard specification, not a `.twb/.twbx` workbook:

- [`docs/tableau_dashboard_spec.md`](tableau_dashboard_spec.md)
- [`docs/dashboard_preview.html`](dashboard_preview.html)

To publish a real workbook:

1. Install **Tableau Public Desktop**.
2. Connect to the CSVs in `outputs/tableau/`.
3. Build the four pages from the specification.
4. Choose **Server → Tableau Public → Save to Tableau Public**.
5. Add the published URL to the README.

Tableau Public requires a free account and manual workbook construction. It is not automated in this repository.

---

## 5. PostgreSQL (optional)

The database path is included for a production-style deployment:

```text
sql/01_schema.sql
sql/02_views.sql
sql/03_quality_checks.sql
scripts/load_postgres.py
```

For a managed database (Neon, Supabase, Railway, RDS):

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://USER:PASSWORD@HOST:5432/supply_chain"
python scripts/load_postgres.py --truncate
```

Then run `sql/03_quality_checks.sql`.

> The SQL is syntax-validated but was not executed against a live PostgreSQL server in the build environment. Validate it against the managed instance before presenting it as production-ready.

---

## 6. Dashboard data snapshot

Tracked under `outputs/tableau/`:

```text
inventory_overview.csv         60 rows  · 106 fields
abc_xyz_summary.csv             9 rows
reorder_alerts.csv              6 rows
supplier_performance.csv       12 rows
purchase_order_lead_times.csv 446 rows
inventory_snapshots.csv     6,300 rows
weekly_demand.csv           6,300 rows
monthly_demand_forecast.csv 1,620 rows
forecast_accuracy.csv           60 rows
demand_forecast.csv            180 rows
```

The total is about 2 MB. Regenerate them at any time:

```bash
python -m inventory_opt.pipeline --regenerate
```

If the committed snapshot is missing or stale, the Streamlit app shows an actionable error and the exact regeneration command.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Pages URL returns 404 | Confirm Settings → Pages uses `main` + `/docs`; wait for the deployment to finish |
| Streamlit app shows missing data | Restore `outputs/tableau/*.csv` or run the pipeline; check the app's error panel |
| Streamlit `ModuleNotFoundError` | Confirm `requirements.txt` is on the app branch and redeploy |
| CI fails on `py_compile app.py` | Install/inspect the Streamlit syntax locally: `python -m py_compile app.py` |
| Charts do not render | Confirm `plotly>=5.24` and `streamlit>=1.50` in `requirements.txt` |
| Tableau fields missing | Re-run `python -m inventory_opt.pipeline --regenerate` and reconnect the extracts |
