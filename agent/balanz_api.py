"""
balanz_api.py
-------------
Cliente HTTP para la API interna de productores.balanz.com.
Todos los endpoints descubiertos via network inspection.
"""

import os
import logging
from datetime import date, datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BALANZ_API  = "https://productores.balanz.com/api/v1"
PRODUCER_ID = os.getenv("BALANZ_PRODUCER_ID", "93139")
TIMEOUT     = 30


class BalanzAPI:
    """
    Cliente para la API de Balanz.
    Recibe cookies de sesión ya autenticadas.
    """

    def __init__(self, cookies: dict):
        self.cookies = cookies
        self._client = httpx.AsyncClient(
            cookies=cookies,
            timeout=TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://productores.balanz.com/",
            }
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{BALANZ_API}/{path}"
        logger.debug(f"GET {url} params={params}")
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ #
    #  Clientes / Cuentas                                                  #
    # ------------------------------------------------------------------ #

    async def buscar_clientes(self, search: str = "") -> list:
        """
        Lista de clientes del productor.
        GET /api/v1/cuentas/{producer_id}?search=texto
        Devuelve: [{id, cuenta, tipo, comitente, cuotapartista, ...}]
        """
        data = await self._get(
            f"cuentas/{PRODUCER_ID}",
            params={"search": search} if search else {}
        )
        return data if isinstance(data, list) else data.get("data", [])

    async def get_todos_los_clientes(self) -> list:
        """Obtiene la lista completa sin filtro. Puede requerir paginación."""
        # El portal requiere al menos 3 chars — usamos búsquedas por letra
        # para simular "todos". Alternativa: buscar por "" si el backend lo permite.
        return await self.buscar_clientes("")

    # ------------------------------------------------------------------ #
    #  Estado de cuenta / Posición                                         #
    # ------------------------------------------------------------------ #

    async def get_estado_cuenta(
        self,
        id_cuenta: int | str,
        fecha: Optional[date] = None,
    ) -> dict:
        """
        Posición consolidada de un cliente.
        GET /api/v1/estadodecuenta/{idCuenta}?Fecha=YYYYMMDD
        Devuelve: saldos, liquidez proyectada, instrumentos
        """
        if fecha is None:
            fecha = date.today()
        fecha_str = fecha.strftime("%Y%m%d")
        return await self._get(
            f"estadodecuenta/{id_cuenta}",
            params={"Fecha": fecha_str}
        )

    # ------------------------------------------------------------------ #
    #  Movimientos                                                          #
    # ------------------------------------------------------------------ #

    async def get_movimientos(
        self,
        id_cuenta: int | str,
        fecha_desde: date,
        fecha_hasta: Optional[date] = None,
    ) -> list:
        """
        Movimientos/transacciones de un cliente en un período.
        GET /api/v1/movimientos/{idCuenta}?FechaDesde=YYYYMMDD&FechaHasta=YYYYMMDD
        Devuelve: [{concertacion, tipo, descripcion, ticker, cantidad, precio,
                    liquidacion, moneda, importe}]
        """
        if fecha_hasta is None:
            fecha_hasta = date.today()
        data = await self._get(
            f"movimientos/{id_cuenta}",
            params={
                "FechaDesde": fecha_desde.strftime("%Y%m%d"),
                "FechaHasta": fecha_hasta.strftime("%Y%m%d"),
            }
        )
        return data if isinstance(data, list) else data.get("data", [])

    # ------------------------------------------------------------------ #
    #  Acreditaciones                                                       #
    # ------------------------------------------------------------------ #

    async def get_acreditaciones(
        self,
        fecha_desde: date,
        fecha_hasta: Optional[date] = None,
    ) -> list:
        """
        Acreditaciones de todos los clientes del productor.
        GET /api/v1/acreditaciones/{producer_id}?FechaDesde=YYYYMMDD&FechaHasta=YYYYMMDD
        Devuelve: [{fechaCarga, horaCarga, comitente, cuenta, fechaAcreditacion,
                    moneda, importe, recibo, asesor}]
        """
        if fecha_hasta is None:
            fecha_hasta = date.today()
        data = await self._get(
            f"acreditaciones/{PRODUCER_ID}",
            params={
                "FechaDesde": fecha_desde.strftime("%Y%m%d"),
                "FechaHasta": fecha_hasta.strftime("%Y%m%d"),
            }
        )
        return data if isinstance(data, list) else data.get("data", [])

    # ------------------------------------------------------------------ #
    #  Notificaciones                                                       #
    # ------------------------------------------------------------------ #

    async def get_notificaciones(self) -> list:
        """GET /api/v1/notificaciones"""
        data = await self._get("notificaciones")
        return data if isinstance(data, list) else data.get("data", [])
