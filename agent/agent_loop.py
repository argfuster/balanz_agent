"""
agent_loop.py
-------------
Loop agentico: Claude decide qué datos buscar, llama las tools,
y genera el informe final en lenguaje natural.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any

import anthropic

from .balanz_session import get_session
from .balanz_api import BalanzAPI

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "buscar_clientes",
        "description": (
            "Busca clientes del productor por nombre o apellido. "
            "Si search está vacío, intenta traer todos. "
            "Devuelve lista con id, cuenta (nombre), comitente, cuotapartista."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Texto a buscar (nombre, apellido). Mínimo 3 chars. Dejar vacío para todos.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_estado_cuenta",
        "description": (
            "Obtiene la posición consolidada de un cliente: "
            "total en pesos, saldo disponible, instrumentos, liquidez proyectada. "
            "Usar id_cuenta del resultado de buscar_clientes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id_cuenta": {
                    "type": "integer",
                    "description": "ID numérico de la cuenta del cliente",
                },
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD. Por defecto: hoy.",
                },
            },
            "required": ["id_cuenta"],
        },
    },
    {
        "name": "get_movimientos",
        "description": (
            "Obtiene movimientos/transacciones de un cliente en un período. "
            "Incluye compras, ventas, suscripciones, rescates, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id_cuenta": {"type": "integer"},
                "fecha_desde": {
                    "type": "string",
                    "description": "Formato YYYY-MM-DD",
                },
                "fecha_hasta": {
                    "type": "string",
                    "description": "Formato YYYY-MM-DD. Por defecto: hoy.",
                },
            },
            "required": ["id_cuenta", "fecha_desde"],
        },
    },
    {
        "name": "get_acreditaciones",
        "description": (
            "Obtiene todas las acreditaciones (ingresos de dinero) "
            "de todos los clientes del productor en un período. "
            "Incluye moneda, importe, tipo (MEP, Cable, pesos)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_desde": {"type": "string", "description": "Formato YYYY-MM-DD"},
                "fecha_hasta": {"type": "string", "description": "Formato YYYY-MM-DD"},
            },
            "required": ["fecha_desde"],
        },
    },
]

SYSTEM_PROMPT = """
Sos un asistente financiero que trabaja para Juan Ignacio Fuster, 
asesor financiero independiente de Nomad Capital Global LLC.

Tenés acceso a la cartera completa de sus clientes en Balanz via herramientas.

Al generar reportes:
- Respondé siempre en español
- Usá formato claro con secciones bien definidas
- Mostrá montos con separadores de miles ($ 1.234.567)
- Indicá fecha y período del reporte
- Si hay múltiples clientes, organizá por cliente
- Sé conciso pero completo — el asesor necesita datos accionables

Hoy es {today}.
"""


async def _execute_tool(name: str, tool_input: dict, api: BalanzAPI) -> Any:
    """Ejecuta la tool que Claude solicitó y devuelve el resultado."""
    try:
        if name == "buscar_clientes":
            return await api.buscar_clientes(tool_input.get("search", ""))

        elif name == "get_estado_cuenta":
            fecha = None
            if "fecha" in tool_input:
                from datetime import date as dt
                fecha = dt.fromisoformat(tool_input["fecha"])
            return await api.get_estado_cuenta(tool_input["id_cuenta"], fecha)

        elif name == "get_movimientos":
            desde = date.fromisoformat(tool_input["fecha_desde"])
            hasta = (
                date.fromisoformat(tool_input["fecha_hasta"])
                if "fecha_hasta" in tool_input
                else date.today()
            )
            return await api.get_movimientos(tool_input["id_cuenta"], desde, hasta)

        elif name == "get_acreditaciones":
            desde = date.fromisoformat(tool_input["fecha_desde"])
            hasta = (
                date.fromisoformat(tool_input["fecha_hasta"])
                if "fecha_hasta" in tool_input
                else date.today()
            )
            return await api.get_acreditaciones(desde, hasta)

        else:
            return {"error": f"Tool desconocida: {name}"}

    except Exception as e:
        logger.error(f"Error ejecutando tool {name}: {e}")
        return {"error": str(e)}


async def run_agent(request: str) -> str:
    """
    Corre el agente completo:
    1. Obtiene sesión autenticada
    2. Loop Claude → tools → Claude hasta respuesta final
    3. Devuelve el informe como string
    """
    # 1. Sesión autenticada (cache o login fresco)
    cookies = await get_session()

    anthropic_client = anthropic.Anthropic()
    today = date.today().strftime("%d/%m/%Y")

    messages = [{"role": "user", "content": request}]

    async with BalanzAPI(cookies) as api:
        iteration = 0
        max_iterations = 10  # Límite de seguridad

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Iteración {iteration}")

            response = anthropic_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT.format(today=today),
                tools=TOOLS,
                messages=messages,
            )

            # Respuesta final — Claude terminó
            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_blocks)

            # Claude quiere usar tools
            if response.stop_reason == "tool_use":
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info(f"→ Tool: {block.name}({json.dumps(block.input, ensure_ascii=False)[:100]})")

                        result = await _execute_tool(block.name, block.input, api)

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        })

                messages.append({
                    "role": "user",
                    "content": tool_results,
                })

            else:
                # stop_reason inesperado
                break

    return "El agente no pudo generar una respuesta. Revisá los logs."
