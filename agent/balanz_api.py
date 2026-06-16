"""
balanz_api.py
-------------
Cliente HTTP para la API de Balanz usando Bearer token.
"""

import os
import logging
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BALANZ_API  = "https://productores.balanz.com/api/v1"
PRODUCER_ID = os.getenv("BALANZ_PRODUCER_ID", "93139")
TIMEOUT     = 30


class BalanzAPI:
    def __init__(self, session: dict):
        self.token = session["token"]
        self.id_sesion = session.get("idSesion")
        self._client = httpx.AsyncClient(
            timeout=TIMEOUT,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Accept-Language": "es-AR,es;q=0.9",
                "Origin": "https://productores.balanz.com",
                "Referer": "https://productores.balanz.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def _get(self, path: str, params: dict = None):
        url = f"{BALANZ_API}/{path}"
        logger.debug(f"GET {url} params={params}")
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    async def buscar_clientes(self, search: str = "") -> list:
        data = await self._get(f"cuentas/{PRODUCER_ID}", params={"search": search} if search else {})
        return data if isinstance(data, list) else data.get("data", [])

    async def get_estado_cuenta(self, id_cuenta, fecha: Optional[date] = None) -> dict:
        if fecha is None:
            fecha = date.today()
        return await self._get(f"estadodecuenta/{id_cuenta}", params={"Fecha": fecha.strftime("%Y%m%d")})

    async def get_movimientos(self, id_cuenta, fecha_desde: date, fecha_hasta: Optional[date] = None) -> list:
        if fecha_hasta is None:
            fecha_hasta = date.today()
        data = await self._get(f"movimientos/{id_cuenta}", params={
            "FechaDesde": fecha_desde.strftime("%Y%m%d"),
            "FechaHasta": fecha_hasta.strftime("%Y%m%d"),
        })
        return data if isinstance(data, list) else data.get("data", [])

    async def get_acreditaciones(self, fecha_desde: date, fecha_hasta: Optional[date] = None) -> list:
        if fecha_hasta is None:
            fecha_hasta = date.today()
        data = await self._get(f"acreditaciones/{PRODUCER_ID}", params={
            "FechaDesde": fecha_desde.strftime("%Y%m%d"),
            "FechaHasta": fecha_hasta.strftime("%Y%m%d"),
        })
        return data if isinstance(data, list) else data.get("data", [])

    async def get_notificaciones(self) -> list:
        data = await self._get("notificaciones")
        return data if isinstance(data, list) else data.get("data", [])
