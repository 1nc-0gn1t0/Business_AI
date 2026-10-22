from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas import BusinessPreferences, BusinessProfile
from app.geo.candidate_policy import business_key, city_key, disperse, fingerprint, metric_srid
from app.geo.candidate_schemas import CandidateRequest, ProximityRequirement
from app.geo.schemas import Bounds


def request(**kwargs: object) -> CandidateRequest:
    return CandidateRequest.model_validate(
        {
            "profile": {"conversation_id": str(uuid4()), "city": "Казань", "category": "кофейня"},
            **kwargs,
        }
    )


def test_policy_and_projection() -> None:
    assert city_key(" Kazan ") == city_key("КАЗАНЬ")
    assert business_key(" Кофейня ") == "coffee"
    assert metric_srid(Bounds(west=49.05, south=55.70, east=49.25, north=55.85)) == 32639
    assert metric_srid(Bounds(west=151, south=-34, east=151.1, north=-33.9)) == 32756
    with pytest.raises(ValueError, match="UTM"):
        metric_srid(Bounds(west=1, east=1.1, south=84.1, north=84.2))


def test_fingerprint_ignores_profile_identity_but_tracks_inputs() -> None:
    first, second = request(), request()
    assert first.profile.id != second.profile.id
    assert fingerprint(first, "a" * 64, 32639) == fingerprint(second, "a" * 64, 32639)
    assert fingerprint(first, "a" * 64, 32639) != fingerprint(first, "b" * 64, 32639)
    assert fingerprint(first, "a" * 64, 32639) != fingerprint(request(limit=3), "a" * 64, 32639)
    a = first.model_copy(
        update={
            "profile": BusinessProfile(
                conversation_id=uuid4(),
                city="Казань",
                category="кофейня",
                budget=Decimal("2000000.00"),
            )
        }
    )
    b = a.model_copy(
        update={
            "profile": a.profile.model_copy(update={"id": uuid4(), "budget": Decimal("2000000")})
        }
    )
    assert fingerprint(a, "a" * 64, 32639) == fingerprint(b, "a" * 64, 32639)


def test_dispersion_is_reproducible_unique_and_respects_separation() -> None:
    rows = [{"i": i, "j": 0, "x": i * 500.0, "y": 0.0} for i in range(6)]
    chosen = disperse(rows, 4, 600)
    assert chosen == disperse(list(reversed(rows)), 4, 600)
    assert len(chosen) >= 2
    assert len({r["i"] for r in chosen}) == len(chosen)
    assert all(abs(a["x"] - b["x"]) >= 600 for a in chosen for b in chosen if a != b)
    assert disperse([], 5, 0) == []
    assert len(disperse(rows, 5, 10000)) == 1


@pytest.mark.parametrize(
    "values",
    [
        {"cell_size_m": 0},
        {"cell_size_m": 249},
        {"limit": 11},
        {"district_ids": [1, 1]},
        {"excluded_district_ids": [-2]},
        {"requirements": [{"category": "rent:cheap", "max_distance_m": 100}]},
        {"requirements": [{"category": "amenity:cafe", "max_distance_m": float("nan")}]},
        {
            "requirements": [
                {"category": "amenity:cafe", "max_distance_m": 100, "profile_constraint": "unknown"}
            ]
        },
    ],
)
def test_invalid_requests(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        request(**values)


def test_explicit_constraint_binding() -> None:
    profile = BusinessProfile(
        conversation_id=uuid4(), preferences=BusinessPreferences(constraints=("остановка",))
    )
    req = ProximityRequirement(
        category="highway:bus_stop", max_distance_m=500, profile_constraint="остановка"
    )
    assert CandidateRequest(profile=profile, requirements=(req,)).requirements == (req,)
