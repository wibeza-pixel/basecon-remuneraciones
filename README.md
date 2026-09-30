# BASECON — Remuneraciones Chile (v2)

```bash
pip install -r requirements.txt
streamlit run app.py          # primer ingreso: crear usuario administrador
python -m pytest -q tests     # pruebas (SQLite); con TEST_DATABASE_URL=... también contra Postgres
```
Para usarla en Streamlit Cloud, configure `DATABASE_URL` (Supabase) y `BASECON_SECRET` en *Settings → Secrets* (vea `.streamlit/secrets.toml.example`).

El detalle de los cambios está en `CAMBIOS.md`.
