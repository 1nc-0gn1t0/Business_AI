"""Read-only HTTP financial demo with an independent integer/Fraction reference."""

import argparse
import copy
import json
import time
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def cents(value: str) -> int:
    exact = Fraction(value) * 100
    assert exact.denominator == 1
    return exact.numerator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "docs/examples/BA-009-coffee-input.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.input.read_text(encoding="utf-8"))
    durations = []

    def run(payload: dict[str, Any]) -> dict[str, Any]:
        req = Request(
            args.api.rstrip("/") + "/api/v1/finance/calculate",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        with urlopen(req, timeout=30) as response:
            result: dict[str, Any] = json.load(response)
        durations.append(round(time.perf_counter() - started, 3))
        return result

    result = run(request)
    assert run(request) == result, "Response must reproduce exactly"
    days = request["working_days_per_month"]["value"]
    for scenario in result["scenarios"]:
        inputs = request["scenarios"][scenario["name"]]
        fixed = inputs.get("fixed_costs") or request["monthly_fixed_costs"]
        fixed_cents = sum(cents(item["value"]) for item in fixed.values())
        check_cents = cents(inputs["average_check"]["value"])
        ratio = Fraction(inputs["variable_cost_ratio"]["value"])
        revenue_cents = check_cents * inputs["sales_per_day"]["value"] * days
        variable = revenue_cents * ratio
        # Positive expense, ROUND_HALF_UP in integer arithmetic; no Decimal/engine helper used.
        variable_cents = (2 * variable.numerator + variable.denominator) // (
            2 * variable.denominator
        )
        need = Fraction(fixed_cents) / (check_cents * (1 - ratio) * days)
        break_even = -(-need.numerator // need.denominator)
        metrics = scenario["metrics"]
        assert cents(metrics["monthly_revenue"]["value"]) == revenue_cents
        assert cents(metrics["monthly_variable_cost"]["value"]) == variable_cents
        assert (
            cents(metrics["operating_result"]["value"])
            == revenue_cents - variable_cents - fixed_cents
        )
        assert int(metrics["break_even_sales_per_day"]["value"]) == break_even
    startup_cents = sum(cents(item["value"]) for item in request["startup"].values())
    assert cents(result["startup"]["total_initial_funding"]) == startup_cents
    assert (
        cents(result["budget"]["remaining"])
        == cents(request["profile"]["budget"]) - startup_cents
    )
    changed = copy.deepcopy(request)
    changed["scenarios"]["base"]["sales_per_day"]["value"] = 90
    recalculated = run(changed)
    assert (
        recalculated["scenarios"][1]["metrics"]["operating_result"]["value"]
        == "226500.00"
    )
    assert recalculated["request_fingerprint"] != result["request_fingerprint"]
    without_zone = copy.deepcopy(request)
    without_zone.pop("selected_zone", None)
    assert run(without_zone)["scenarios"] == result["scenarios"]
    checks = {
        "independent_fraction_reference_three_scenarios": True,
        "startup_and_budget": True,
        "exact_replay": True,
        "edit_and_recalculate": True,
        "zone_does_not_change_finance": True,
    }
    report = {
        "input_file": args.input.name,
        "checks": checks,
        "http_seconds": durations,
        "response": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"checks": checks, "http_seconds": durations, "output": str(args.output)},
            ensure_ascii=False,
        )
    )
    for scenario in result["scenarios"]:
        print(
            json.dumps(
                {
                    "name": scenario["name"],
                    "metrics": {
                        key: item["value"] for key, item in scenario["metrics"].items()
                    },
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
