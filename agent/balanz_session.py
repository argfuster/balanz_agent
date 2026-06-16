"""
balanz_session.py
"""

import json
import os
import logging
from datetime import datetime, timedelta, timezone

import httpx
from playwright.async_api import async_playwright
from supabase import create_client, Client

logger = logging.getLogger(__name__)

BALANZ_BASE = "https://productores.balanz.com"
BALANZ_API  = f"{BALANZ_BASE}/api/v1"
SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", 4))
PRODUCER_ID = os.getenv("BALANZ_PRODUCER_ID", "93139")
HEADLESS    = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"


def _get_supabase() -> Client:
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY"),
    )


async def _validate_session(cookies: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BALANZ_API}/notificaciones",
                cookies=cookies,
                headers={"Referer": f"{BALANZ_BASE}/"},
            )
            return r.status_code == 200
    except Exception:
        return False


async def _playwright_login(username: str, password: str) -> dict:
    logger.info(f"Iniciando login (headless={HEADLESS})...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox"] if HEADLESS else []
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # Ir al portal — redirige al login si no hay sesión
        await page.goto(f"{BALANZ_BASE}/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        logger.info(f"URL inicial: {page.url}")

        # Completar login si estamos en la página de login
        if "login" in page.url.lower() or "Pages" in page.url:
            await page.fill("input[placeholder*='Usuario']", username)
            await page.fill("input[placeholder*='Clave']", password)
            await page.wait_for_timeout(500)
            await page.click("a:has-text('Ingresar')")
            await page.wait_for_load_state("networkidle", timeout=20000)
            await page.wait_for_timeout(3000)

        logger.info(f"URL post-login: {page.url}")

        # Esperar a que cargue el frame de asesores
        await page.wait_for_timeout(2000)

        # Capturar cookies de todos los contextos (incluyendo frames)
        raw_cookies = await context.cookies()
        await browser.close()

    cookies = {c["name"]: c["value"] for c in raw_cookies}
    logger.info(f"Login completado. {len(cookies)} cookies: {list(cookies.keys())}")
    return cookies


async def get_session() -> dict:
    supabase = _get_supabase()

    # 1. Buscar sesión cacheada en Supabase
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
                cookies = json.loads(row["cookies"])
                if await _validate_session(cookies):
                    logger.info(f"Sesión cacheada válida (edad: {age})")
                    return cookies
                logger.info("Sesión cacheada inválida — renovando...")
    except Exception as e:
        logger.warning(f"Error leyendo Supabase: {e}")

    # 2. Login fresco
    username = os.getenv("BALANZ_USER")
    password = os.getenv("BALANZ_PASS")
    if not username or not password:
        raise ValueError("BALANZ_USER y BALANZ_PASS deben estar definidos")

    cookies = await _playwright_login(username, password)

    if not await _validate_session(cookies):
        raise ValueError("Login completado pero la sesión no es válida. Revisá credenciales.")

    # 3. Guardar en Supabase
    try:
        supabase.table("balanz_sessions").insert({
            "cookies": json.dumps(cookies),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        logger.info("Sesión guardada en Supabase")
    except Exception as e:
        logger.warning(f"No se pudo guardar sesión: {e}")

    return cookies
