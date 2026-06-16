"""
balanz_session.py
-----------------
Login directo via API REST — sin Playwright.
POST /api/v1/auth/login → AccessToken + idSesion
"""

import json
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone

import httpx
from supabase import create_client, Client

logger = logging.getLogger(__name__)

BALANZ_BASE = "https://productores.balanz.com"
BALANZ_API  = f"{BALANZ_BASE}/api/v1"
SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", 8))


def _get_supabase() -> Client:
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY"),
    )


def _headers(token: str = None) -> dict:
    h = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "es-AR,es;q=0.9",
        "Origin": BALANZ_BASE,
        "Referer": f"{BALANZ_BASE}/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def _validate_session(token: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BALANZ_API}/notificaciones",
                headers=_headers(token),
            )
            return r.status_code == 200
    except Exception:
        return False


async def _api_login(username: str, password: str) -> dict:
    """Login directo via API. Devuelve {token, idSesion, idPersona}."""
    logger.info("Iniciando login via API...")

    nonce = str(uuid.uuid4()).upper()
    dispositivo_id = str(uuid.uuid4())
    payload = {
        "data": {
            "user": username,
            "pass": password,
            "nonce": nonce,
            "source": "WebV1",
            "idDispositivo": dispositivo_id,
            "TipoDispositivo": "Web",
            "Nombre": "Windows 10 Chrome 124.0.0.0",
            "SistemaOperativo": "Windows",
            "VersionSO": "10",
            "VersionAPP": "1.0.0",
            "aa": 1,
        }
    }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # Usar cookiesession1 desde variable de entorno o hacer GET para obtenerla
        session_cookie = os.getenv("BALANZ_SESSION_COOKIE")
        if session_cookie:
            client.cookies.set("cookiesession1", session_cookie, domain="productores.balanz.com")
            logger.info("Usando cookiesession1 desde variable de entorno")
        else:
            await client.get(f"{BALANZ_BASE}/", headers=_headers())
            await client.get(f"{BALANZ_BASE}/Pages/login.html", headers=_headers())
            logger.info(f"Init cookies: {dict(client.cookies)}")

        # POST login
        r = await client.post(
            f"{BALANZ_API}/auth/login",
            json=payload,
            headers=_headers(),
        )

    if r.status_code != 200:
        raise ValueError(f"Login fallido — status {r.status_code}: {r.text[:200]}")

    data = r.json()
    token = data.get("AccessToken")
    id_sesion = data.get("idSesion")
    id_persona = data.get("idPersona")

    if not token:
        raise ValueError(f"Login OK pero sin AccessToken. Respuesta: {data}")

    logger.info(f"Login exitoso — idPersona: {id_persona}, idSesion: {id_sesion}")
    return {
        "token": token,
        "idSesion": id_sesion,
        "idPersona": id_persona,
    }


async def get_session() -> dict:
    """
    Devuelve {token, idSesion, idPersona} válidos.
    Cachea en Supabase por SESSION_TTL horas.
    """
    supabase = _get_supabase()

    # 1. Buscar sesión cacheada
    try:
        result = (
            supabase.table("balanz_sessions")
            .select("*")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - created
            if age < timedelta(hours=SESSION_TTL):
                session = json.loads(row["cookies"])
                if await _validate_session(session.get("token")):
                    logger.info(f"Sesión cacheada válida (edad: {age})")
                    return session
                logger.info("Sesión cacheada inválida — renovando...")
    except Exception as e:
        logger.warning(f"Error leyendo Supabase: {e}")

    # 2. Login fresco
    username = os.getenv("BALANZ_USER")
    password = os.getenv("BALANZ_PASS")
    if not username or not password:
        raise ValueError("BALANZ_USER y BALANZ_PASS deben estar definidos")

    session = await _api_login(username, password)

    # 3. Guardar en Supabase
    try:
        supabase.table("balanz_sessions").insert({
            "cookies": json.dumps(session),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        logger.info("Sesión guardada en Supabase")
    except Exception as e:
        logger.warning(f"No se pudo guardar sesión: {e}")

    return session
