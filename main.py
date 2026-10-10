"""HarvestV API: the 'front desk' between the website and NASA data sources."""
import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from services.nasa_power import NasaPowerBadData, NasaPowerError, NasaPowerTimeout, fetch_weather

log = logging.getLogger("harvestv")
app = FastAPI(title="HarvestV API", version="0.1.0")

# Allowed browser origins (scheme + host + port, no path). Override on Render with the
# ALLOWED_ORIGINS env var, e.g. "https://yourname.github.io". Comma-separated.
DEFAULT_ORIGINS = ("http://localhost:5500,http://127.0.0.1:5500,"
                   "http://localhost:8080,http://127.0.0.1:8080,http://localhost:3000")
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])


@app.get("/")
def health():
    return {"service": "HarvestV API", "status": "ok"}


@app.get("/api/environment")
def get_environment(latitude: float = Query(..., ge=-90, le=90),
                    longitude: float = Query(..., ge=-180, le=180)):
    """Normalized environmental data for a point. Invalid coordinates -> 422 (FastAPI validation)."""
    try:
        weather = fetch_weather(latitude, longitude)
    except NasaPowerTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except (NasaPowerBadData, NasaPowerError) as exc:
        log.warning("NASA POWER failure: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "weather": weather,
        # Future sources: fill these in (and set the source name) when SMAP / MODIS are added.
        "soil": {"moisture": None},
        "vegetation": {"ndvi": None},
        "sources": {"weather": "NASA POWER", "soil": None, "vegetation": None},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
