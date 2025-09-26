from fastapi import FastAPI

from deps import lifespan
import routers


app = FastAPI(title="Homelab Machines API", version="2.0.0", lifespan=lifespan)

# Register routes
app.include_router(routers.router)


@app.get("/")
async def root():
    return {"ok": True, "service": "Homelab Machines API"}
