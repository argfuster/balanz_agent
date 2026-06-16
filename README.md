# Balanz Agent — Nomad Capital

Agente IA que accede al portal de productores de Balanz, extrae datos de clientes
y genera reportes usando Claude.

## Arquitectura

```
FastAPI (Railway)
    └── agent_loop.py     ← Loop Claude + tools
        ├── balanz_session.py  ← Login Playwright + cache Supabase
        └── balanz_api.py      ← Endpoints HTTP con cookies
```

## Setup local

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

### 3. Crear tabla en Supabase

Ejecutar `supabase_setup.sql` en el SQL Editor de Supabase.

### 4. Correr

```bash
uvicorn main:app --reload
```

### 5. Probar

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{"request": "Dame las acreditaciones de esta semana"}'
```

## Deploy en Railway

1. Push al repo
2. Conectar repo en Railway
3. Configurar variables de entorno en Railway dashboard:
   - `BALANZ_USER`
   - `BALANZ_PASS`
   - `BALANZ_PRODUCER_ID` = 93139
   - `ANTHROPIC_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SESSION_TTL_HOURS` = 4

Railway usará `railway.toml` para instalar Chromium automáticamente.

## Endpoints API

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/agent/run` | Ejecutar agente con un pedido |

## Ejemplos de requests al agente

```json
{"request": "Dame las acreditaciones de esta semana"}
{"request": "Cuál es la posición actual del cliente Salerno?"}
{"request": "Movimientos del último mes del cliente 1430009"}
{"request": "Resumen de cartera de todos mis clientes"}
{"request": "Qué clientes acreditaron dólares este mes?"}
```

## Endpoints Balanz descubiertos

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/v1/cuentas/{producer_id}?search=` | Lista clientes |
| `GET /api/v1/estadodecuenta/{id}?Fecha=YYYYMMDD` | Posición consolidada |
| `GET /api/v1/movimientos/{id}?FechaDesde=&FechaHasta=` | Movimientos |
| `GET /api/v1/acreditaciones/{producer_id}?FechaDesde=&FechaHasta=` | Acreditaciones |
