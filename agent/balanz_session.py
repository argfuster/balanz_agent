"""
balanz_session.py
-----------------
Maneja la autenticación con productores.balanz.com.
- Login via Playwright (headless)
- Cachea cookies en Supabase con TTL configurable
- Renueva la sesión automáticamente cuando expira
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


def _get_supabase() -> Client:
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY"),
    )


async def _playwright_login(username: str, password: str) -> dict:
    """
    Abre un browser headless, completa el login en Balanz
    y devuelve las cookies de sesión como dict.
    """
    logger.info("Iniciando login en Balanz via Playwright...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # 1. Cargar página de login
        await page.goto(f"{BALANZ_BASE}/", wait_until="networkidle")

        # 2. Detectar campos de login (el portal usa distintos selectores)
        selectors_user = [
            "input[name='usuario']",
            "input[name='user']",
            "input[type='text']:visible",
            "input[placeholder*='usu']:visible",
        ]
        selectors_pass = [
            "input[name='password']",
            "input[type='password']:visible",
        ]

        user_field = None
        for sel in selectors_user:
            if await page.locator(sel).count() > 0:
                user_field = sel
                break

        pass_field = None
        for sel in selectors_pass:
            if await page.locator(sel).count() > 0:
                pass_field = sel
                break

        if not user_field:
            logger.warning("No se encontró campo de usuario — puede que ya haya sesión activa")
        else:
            # Fill usuario
            await page.click(user_field)
            await page.fill(user_field, username)
            await page.wait_for_timeout(1000)

            # El campo password está oculto en el DOM — usamos JS para llenarlo
            await page.evaluate(
                """(password) => {
                    const inputs = document.querySelectorAll('input[type=\"password\"]');
                    for (const el of inputs) {
                        el.removeAttribute('style');
                        el.style.display = 'block';
                        el.value = password;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""",
                password
            )
            await page.wait_for_timeout(500)

            # Submit via JS
            await page.evaluate(
                """() => {
                    const btn = document.querySelector('button[type=\"submit\"], input[type=\"submit\"], button.btn-login, #btn-login');
                    if (btn) btn.click();
                }"""
            )
            await page.wait_for_load_state("networkidle", timeout=15000)

        # 3. Verificar que estamos en home autenticado
        current_url = page.url
        if "login" in current_url or current_url == f"{BALANZ_BASE}/":
            await browser.close()
            raise ValueError("Login fallido — verificá las credenciales")

        # 4. Extraer cookies
        raw_cookies = await context.cookies()
        await browser.close()

    cookies = {c["name"]: c["value"] for c in raw_cookies}
    logger.info(f"Login exitoso. {len(cookies)} cookies obtenidas.")
    return cookies


async def _validate_session(cookies: dict) -> bool:
    """Hace una llamada liviana a la API para verificar que las cookies son válidas."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BALANZ_API}/notificaciones",
                cookies=cookies,
            )
            return r.status_code == 200
    except Exception:
        return False


async def get_session() -> dict:
    """
    Punto de entrada principal.
    Devuelve cookies válidas, renovando la sesión si es necesario.
    """
    supabase = _get_supabase()

    # 1. Buscar sesión guardada en Supabase
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
                # Validar que la sesión sigue activa
                if await _validate_session(cookies):
                    logger.info(f"Sesión cacheada válida (edad: {age})")
                    return cookies
                else:
                    logger.info("Sesión cacheada expirada — renovando...")
    except Exception as e:
        logger.warning(f"Error leyendo sesión de Supabase: {e}")

    # 2. Hacer login fresco
    username = os.getenv("BALANZ_USER")
    password = os.getenv("BALANZ_PASS")

    if not username or not password:
        raise ValueError("BALANZ_USER y BALANZ_PASS deben estar definidos en .env")

    cookies = await _playwright_login(username, password)

    # 3. Guardar en Supabase
    try:
        supabase.table("balanz_sessions").insert({
            "cookies": json.dumps(cookies),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        logger.info("Sesión guardada en Supabase")
    except Exception as e:
        logger.warning(f"No se pudo guardar sesión en Supabase: {e}")

    return cookies
