# HarvestV API (Stage 1: NASA POWER)
FastAPI backend that sits between the HarvestV website and NASA. The browser never calls NASA directly.

## Run locally
    cd harvestv-api
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    uvicorn main:app --reload
Open http://localhost:8000/docs for the interactive docs.

## Endpoint
`GET /api/environment?latitude=24.75&longitude=90.40`

    {
      "location": {"latitude": 24.75, "longitude": 90.4},
      "weather": {"temperature": 28.2, "rainfall": 14.0, "rainfall_days": 7,
                  "solar_radiation": 18.0, "solar_radiation_units": "MJ/m^2/day", "data_date": "2026-10-03"},
      "soil": {"moisture": null},
      "vegetation": {"ndvi": null},
      "sources": {"weather": "NASA POWER", "soil": null, "vegetation": null},
      "generated_at": "2026-10-06T09:30:00+00:00"
    }
(Illustrative values.) `soil` and `vegetation` stay `null` until NASA SMAP and MODIS are added.

Errors: `422` invalid coordinates, `502` NASA error or unusable data, `504` NASA timeout. Body: `{"detail": "..."}`.

## NASA POWER
Daily point API, community `AG`, last 14 days requested. Parameters: `T2M` (air temperature at 2 m, mean, deg C), `PRECTOTCORR` (corrected precipitation, mm/day, summed over the latest 7 valid days), `ALLSKY_SFC_SW_DWN` (sunlight reaching the ground; units read from NASA's response). This is recent data, not live: the newest days lag by a few days, so `data_date` is the latest valid day. Code: `services/nasa_power.py`. To add SMAP/MODIS, create `services/nasa_smap.py` etc. and fill `soil` / `vegetation` in `main.py`.

## CORS
Allowed origins come from the `ALLOWED_ORIGINS` env var (comma-separated, origin only, no path). Default: localhost ports 5500, 8080, 3000. For GitHub Pages use `https://YOURNAME.github.io`.

## Deploy to Render
New Web Service from the repo, root directory `harvestv-api`. Build: `pip install -r requirements.txt`. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `ALLOWED_ORIGINS` to your GitHub Pages origin. Then set `apiBaseUrl` in the frontend's `js/config.js` to the Render URL. (Free instances sleep, so the first request can be slow.)
