from fastapi import FastAPI
from app.agent.router import router as agent_router
from app.catalog.router import router as catalog_router

app = FastAPI(
    title="Agentic Commerce Gateway",
    description="Merchant-side gateway enabling AI shopping agents to transact under bounded, auditable policy mandates.",
    version="1.0.0"
)

# Mount routers
app.include_router(catalog_router)
app.include_router(agent_router)


@app.get("/health", tags=["system"], summary="Health check endpoint")
def health_check() -> dict:
    """
    Returns the operational status of the gateway services.
    """
    return {
        "status": "healthy",
        "service": "catalog",
        "version": "1.0.0"
    }
