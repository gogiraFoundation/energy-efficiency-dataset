# Dashboard

- **Entry point:** `app.py` — all pages are `render_*` functions and sidebar navigation; there is no `pages/` subfolder (Streamlit multipage is not used here).
- **Queries:** `queries_*.py` modules; shared DB helpers in `db.py`.
- **Marts:** Built by `python -m pipeline.orchestrate marts` from every `sql/marts/NN_*.sql` script, not from `pipeline/transform/run_marts.sql` (which is a non-executed note).

Run from repo root:

```bash
streamlit run dashboard/app.py
```
