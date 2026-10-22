import pytest
from pydantic import ValidationError

from app.geo.ranking_schemas import RawGeoMetrics, ScoringConfig, ScoringWeights
from app.geo.scoring import normalize_values, resolve_policy, score_components


def raw(count: int, covered: bool = True) -> RawGeoMetrics:
    return RawGeoMetrics(
        coverage_margin_m=1000,
        fully_covered=covered,
        mapped_poi_count=count * 3,
        transit_count=count,
        nearest_transit_m=100 if count else None,
        competitor_count=count,
        nearest_competitor_m=50 if count else None,
        competitor_features_per_km2=count,
        infrastructure_count=count,
        infrastructure_categories=("amenity:bank",) if count else (),
        complementary_count=count,
        category_counts={},
    )


def test_normalization_and_constant_cases() -> None:
    assert normalize_values([0, 5, 10]) == [0, 0.5, 1]
    assert normalize_values([0, 5, 10], reverse=True) == [1, 0.5, 0]
    assert normalize_values([3, 3]) == [0.5, 0.5]
    assert normalize_values([0, 0]) == [None, None]
    assert normalize_values([]) == []


def test_weights_no_hidden_redistribution_and_competition_neutrality() -> None:
    metrics = {"a": raw(1), "b": raw(2)}
    config = ScoringConfig()
    components, comparable = score_components(metrics, config)
    assert comparable == ("a", "b")
    assert components["a"][-1].status == "disabled"
    assert components["a"][-1].weight == 0
    assert sum(c.contribution or 0 for c in components["b"]) > sum(
        c.contribution or 0 for c in components["a"]
    )
    assert all(c.weight == pytest.approx(1 / 3) for c in components["a"][:3])
    metrics["a"] = metrics["a"].model_copy(update={"competitor_count": 100})
    changed, _ = score_components(metrics, config)
    assert [c.contribution for c in changed["a"]] == [c.contribution for c in components["a"]]


def test_coverage_missing_data_and_single_candidate_do_not_rank() -> None:
    components, comparable = score_components(
        {"a": raw(1), "edge": raw(10, False)}, ScoringConfig()
    )
    assert comparable == ()
    assert components["edge"][0].status == "outside_coverage"
    assert components["a"][0].contribution is None
    components, comparable = score_components({"a": raw(0), "b": raw(0)}, ScoringConfig())
    assert comparable == ()
    assert components["a"][0].status == "unavailable"
    base, _ = score_components({"a": raw(1), "b": raw(2)}, ScoringConfig())
    mixed, comparable = score_components(
        {"a": raw(1), "b": raw(2), "edge": raw(999, False)}, ScoringConfig()
    )
    assert comparable == ("a", "b")
    assert mixed["a"] == base["a"] and mixed["b"] == base["b"]


def test_custom_weights_and_explicit_competitor_modes() -> None:
    metrics = {"a": raw(1), "b": raw(10)}
    weights = ScoringWeights(transit=0, infrastructure=0, complementary=0, competitors=1)
    for mode, first in (("cluster", 0), ("separation", 100)):
        config = ScoringConfig.model_validate(
            {"weights": weights.model_dump(), "competitor_mode": mode}
        )
        components, comparable = score_components(metrics, config)
        assert comparable == ("a", "b")
        assert components["a"][-1].contribution == first


def test_weight_changes_reverse_relative_preference_and_equal_values_are_neutral() -> None:
    metrics = {"a": raw(1), "b": raw(10).model_copy(update={"nearest_transit_m": 400.0})}
    transit, _ = score_components(
        metrics, ScoringConfig(weights=ScoringWeights(transit=1, infrastructure=0, complementary=0))
    )
    context, _ = score_components(
        metrics, ScoringConfig(weights=ScoringWeights(transit=0, infrastructure=0, complementary=1))
    )
    assert transit["a"][0].contribution == 100 and transit["b"][0].contribution == 0
    assert context["a"][2].contribution == 0 and context["b"][2].contribution == 100
    tied, comparable = score_components({"b": raw(1), "a": raw(1)}, ScoringConfig())
    assert comparable == ("a", "b")
    assert sum(c.contribution or 0 for c in tied["a"]) == pytest.approx(50)
    assert sum(c.contribution or 0 for c in tied["b"]) == pytest.approx(50)


def test_policy_categories_and_versions_follow_business_not_budget() -> None:
    coffee = resolve_policy("кофейня", ScoringConfig())
    bakery = resolve_policy("пекарня", ScoringConfig())
    assert coffee.competitors == ("amenity:cafe",)
    assert bakery.competitors == ("shop:bakery",)
    assert coffee.fingerprint != bakery.fingerprint
    assert coffee.fingerprint == resolve_policy("coffee", ScoringConfig()).fingerprint
    assert coffee.fingerprint != resolve_policy("coffee", ScoringConfig(radius_m=300)).fingerprint
    replayed = ScoringConfig.model_validate(ScoringConfig().model_dump(mode="json"))
    assert coffee.fingerprint == resolve_policy("coffee", replayed).fingerprint


@pytest.mark.parametrize(
    "config",
    [
        {"radius_m": 0},
        {"radius_m": 2001},
        {"weights": {"transit": -1}},
        {"weights": {"transit": float("nan")}},
        {"version": "unknown"},
        {"weights": {"competitors": 1}},
        {"competitor_mode": "cluster"},
        {"weights": {"transit": 0, "infrastructure": 0, "complementary": 0, "competitors": 0}},
    ],
)
def test_invalid_configs(config: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScoringConfig.model_validate(config)
