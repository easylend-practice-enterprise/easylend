from fastapi import FastAPI

app = FastAPI(
    title="EasyLend API",
    description="Core Backend for the EasyLend Practice Enterprise",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to the EasyLend API!",
        "docs_url": "/docs"
    }

@app.get("/api/v1/health")
async def health_check():
    """
    Simpel endpoint voor Uptime Kuma om te checken of de API ademt.
    Later breiden we dit uit met een DB en Redis check.
    """
    return {"status": "healthy", "components": {"api": "ok"}}