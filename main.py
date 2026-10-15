"""HarvestV API: the 'front desk' between the website and NASA data sources."""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database.database import get_crop, init_db, list_crops
from services.nasa_power import NasaPowerBadData, NasaPowerError, NasaPowerTimeout, fetch_weather

log = logging.getLogger("harvestv")


@asynccontextmanager
async def lifespan(_app):
    # Rebuild/sync the crop database from the committed seed file on every start (Render's disk is not persistent).
    log.info("Crop database ready: %s crops", init_db())
    yield


app = FastAPI(title="HarvestV API", version="0.2.0", lifespan=lifespan)

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


# ---------- Stage 2: crop database ----------
class Crop(BaseModel):
    id: str
    name: str
    emoji: str | None = None
    season: str
    description: str | None = None
    growing_duration: str | None = None
    temperature_range: str | None = None
    soil_moisture: str | None = None
    soil_requirements: str | None = None
    nitrogen_requirement: str | None = None
    fertilizer_notes: str | None = None
    water_requirement: str | None = None
    water_demand_score: float | None = None
    pest_disease_notes: str | None = None
    drought_tolerance: str | None = None
    is_legume: bool
    preceding_crops: list[str]
    following_crops: list[str]


class CropList(BaseModel):
    count: int
    crops: list[Crop]


@app.get("/api/crops", response_model=CropList)
def get_crops():
    """All crops in the order the website shows them. Records are small, so the full record is returned
    (the rotation pages need every field for every crop)."""
    crops = list_crops()
    return {"count": len(crops), "crops": crops}


@app.get("/api/crops/{crop_id}", response_model=Crop, responses={404: {"description": "Crop not found"}})
def get_crop_by_id(crop_id: str):
    crop = get_crop(crop_id)
    if crop is None:
        raise HTTPException(status_code=404, detail=f"Crop '{crop_id}' not found.")
    return crop
