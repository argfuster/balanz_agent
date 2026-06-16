"""
main.py
-------
FastAPI app para el agente Balanz.
Deploy en Railway.
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from agent.agent_loop import run_agent

app = FastAPI(
    title="Balanz Agent — Nomad Capital",
    description="Agente IA para reportes de cartera Balanz",
    version="1.0.0",
)


class AgentRequest(BaseModel):
    request: str  # Ej: "Dame los movimientos del último mes de todos mis clientes"


class AgentResponse(BaseModel):
    result: str
    status: str = "ok"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/agent/run", response_model=AgentResponse)
async def run(req: AgentRequest):
    """
    Ejecuta el agente con el pedido del usuario.

    Ejemplos de requests:
    - "Dame las acreditaciones de esta semana"
    - "Cuál es la posición actual del cliente Salerno?"
    - "Mostrá los movimientos del último mes del cliente 1430009"
    - "Generá un resumen de cartera de todos mis clientes"
    """
    if not req.request.strip():
        raise HTTPException(status_code=400, detail="El request no puede estar vacío")

    try:
        result = await run_agent(req.request)
        return AgentResponse(result=result)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logging.error(f"Error en agente: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@app.get("/")
async def root():
    return {
        "app": "Balanz Agent",
        "producer": os.getenv("BALANZ_PRODUCER_ID", "no configurado"),
        "docs": "/docs",
    }
