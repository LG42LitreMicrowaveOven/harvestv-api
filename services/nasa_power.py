"""NASA POWER client. Fetches recent daily data for one point and normalizes it for HarvestV.

Docs: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
Parameters used (community "AG" = agroclimatology):
  T2M                Air temperature at 2 m, daily mean (deg C)
  PRECTOTCORR        Bias-corrected precipitation (mm/day)
  ALLSKY_SFC_SW_DWN  All-sky surface shortwave downward irradiance (sunlight reaching the ground)
NASA POWER daily data is NOT live: the newest days are typically a few days behind, so we report
the latest available day. Missing values are flagged by NASA as -999 and are skipped here.
"""
from datetime import date, timedelta

import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN"
LOOKBACK_DAYS = 14        # request window; enough to find recent valid days
RAINFALL_WINDOW_DAYS = 7  # rainfall is summed over the latest 7 valid days
TIMEOUT_SECONDS = 20
FILL_VALUE = -999


class NasaPowerError(Exception):
    """NASA POWER could not be reached or returned an error status."""


class NasaPowerTimeout(NasaPowerError):
    """NASA POWER did not answer in time."""


class NasaPowerBadData(NasaPowerError):
    """NASA POWER answered, but not with data we can use."""


def _valid_series(parameter_block: dict, name: str) -> list:
    """Sorted [(YYYYMMDD, value)] without NASA fill values."""
    series = parameter_block.get(name)
    if not isinstance(series, dict):
        raise NasaPowerBadData(f"NASA POWER response is missing {name}.")
    return sorted((d, v) for d, v in series.items()
                  if isinstance(v, (int, float)) and v != FILL_VALUE)


def _iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def normalize_power_response(payload: dict) -> dict:
    """Raw NASA POWER JSON -> HarvestV 'weather' block. Raises NasaPowerBadData if unusable."""
    try:
        block = payload["properties"]["parameter"]
    except (KeyError, TypeError):
        raise NasaPowerBadData("NASA POWER response had an unexpected format.")
    temp = _valid_series(block, "T2M")
    rain = _valid_series(block, "PRECTOTCORR")
    solar = _valid_series(block, "ALLSKY_SFC_SW_DWN")
    if not (temp and rain and solar):
        raise NasaPowerBadData("NASA POWER has no valid recent data for this location.")
    recent_rain = rain[-RAINFALL_WINDOW_DAYS:]
    units = (payload.get("parameters") or {}).get("ALLSKY_SFC_SW_DWN", {}).get("units")
    return {
        "temperature": round(temp[-1][1], 1),
        "rainfall": round(sum(v for _, v in recent_rain), 1),
        "rainfall_days": len(recent_rain),
        "solar_radiation": round(solar[-1][1], 1),
        # Units come from NASA's own metadata; fallback is the AG-community unit.
        "solar_radiation_units": units or "MJ/m²/day",
        "data_date": _iso(temp[-1][0]),
    }


def fetch_weather(latitude: float, longitude: float) -> dict:
    end = date.today()
    params = {
        "parameters": PARAMETERS, "community": "AG",
        "latitude": latitude, "longitude": longitude,
        "start": (end - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"), "format": "JSON",
    }
    try:
        resp = requests.get(POWER_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.Timeout:
        raise NasaPowerTimeout("NASA POWER took too long to respond.")
    except requests.RequestException as exc:
        raise NasaPowerError(f"Could not reach NASA POWER: {exc.__class__.__name__}")
    if resp.status_code != 200:
        raise NasaPowerError(f"NASA POWER returned HTTP {resp.status_code}.")
    try:
        payload = resp.json()
    except ValueError:
        raise NasaPowerBadData("NASA POWER returned a non-JSON response.")
    return normalize_power_response(payload)
