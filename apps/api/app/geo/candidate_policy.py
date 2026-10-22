import hashlib
import json
import math
from typing import Any

from app.geo.candidate_schemas import CandidateRequest
from app.geo.schemas import Bounds

ALGORITHM_VERSION = "utm-grid-dispersion-v1"
POLICY_VERSION = "osm-anchor-policy-v1"
# These are observable context, not evidence of demand or available premises.
POLICIES: dict[str, tuple[str, ...]] = {
    "coffee": ("amenity:cafe", "amenity:university", "amenity:college", "highway:bus_stop"),
    "bakery": ("shop:bakery", "shop:supermarket", "highway:bus_stop"),
    "restaurant": ("amenity:restaurant", "amenity:cafe", "highway:bus_stop"),
    "salon": ("shop:hairdresser", "shop:supermarket", "highway:bus_stop"),
    "grocery": ("shop:supermarket", "shop:convenience", "highway:bus_stop"),
}
ALIASES = {
    "кофейня": "coffee",
    "кафе": "coffee",
    "coffee shop": "coffee",
    "cafe": "coffee",
    "пекарня": "bakery",
    "ресторан": "restaurant",
    "салон красоты": "salon",
    "продуктовый магазин": "grocery",
}
NOT_EVALUATED = (
    "Zones are geographic search areas, not available premises or buildable parcels.",
    "Budget, funding and business format are preserved, but affordability, floor area and "
    "legal suitability cannot be checked with OSM POI data.",
    "No ranking, measured traffic, demand, rent, revenue or profitability is calculated.",
    "OSM presence is evidence of mapped context only; missing objects do not prove absence.",
    "Proximity uses straight-line distances from a representative point, not walking routes "
    "or a guarantee for every location inside the zone.",
)


def normalize(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def city_key(value: str) -> str:
    result = normalize(value)
    return "казань" if result == "kazan" else result


def business_key(value: str) -> str:
    result = normalize(value)
    return ALIASES.get(result, result)


def metric_srid(bounds: Bounds) -> int:
    longitude = (bounds.west + bounds.east) / 2
    latitude = (bounds.south + bounds.north) / 2
    if bounds.south < -80 or bounds.north > 84 or bounds.east - bounds.west > 3:
        raise ValueError("Dataset exceeds supported local UTM extent")
    zone = min(60, math.floor((longitude + 180) / 6) + 1)
    return (32600 if latitude >= 0 else 32700) + zone


def fingerprint(request: CandidateRequest, version: str, srid: int) -> str:
    values = request.model_dump(mode="json")
    for key in ("id", "conversation_id", "confirmation_state"):
        values["profile"].pop(key)
    if request.profile.budget is not None:
        values["profile"]["budget"] = format(request.profile.budget.normalize(), "f")
    values["data_version"] = version
    for key in ("district_ids", "excluded_district_ids"):
        values[key] = sorted(values[key])
    payload = [ALGORITHM_VERSION, POLICY_VERSION, srid, values]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def disperse(rows: list[dict[str, Any]], limit: int, separation: float) -> list[dict[str, Any]]:
    """Farthest-point geographic sampling. No commercial score or weights."""
    if not rows:
        return []
    center_x = sum(row["x"] for row in rows) / len(rows)
    center_y = sum(row["y"] for row in rows) / len(rows)
    remaining = sorted(rows, key=lambda row: (row["i"], row["j"]))
    first = min(
        remaining,
        key=lambda r: ((r["x"] - center_x) ** 2 + (r["y"] - center_y) ** 2, r["i"], r["j"]),
    )
    selected = [first]
    remaining.remove(first)
    while remaining and len(selected) < limit:

        def distance(row: dict[str, Any]) -> float:
            return min(math.hypot(row["x"] - r["x"], row["y"] - r["y"]) for r in selected)

        chosen = max(remaining, key=lambda r: (distance(r), -r["i"], -r["j"]))
        if distance(chosen) < separation:
            break
        selected.append(chosen)
        remaining.remove(chosen)
    return selected
