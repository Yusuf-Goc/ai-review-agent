import json
from typing import Any


FULL_SCAN_STAT_KEYS = [
    "planned_units",
    "first_pass_success",
    "first_pass_failed",
    "second_pass_success",
    "second_pass_failed",
    "fallback_units",
    "fallback_pass_success",
    "final_failed_units",
    "total_successful_units",
]


def _load_worker_result(
    result_path: str,
) -> dict[str, Any]:
    try:
        with open(
            result_path,
            "r",
            encoding="utf-8",
        ) as result_file:
            result = json.load(result_file)

    except FileNotFoundError as exc:
        raise ValueError(
            f"Full scan worker sonucu bulunamadı: "
            f"{result_path}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Full scan worker sonucu geçerli JSON değil: "
            f"{result_path}"
        ) from exc

    if not isinstance(result, dict):
        raise ValueError(
            "Full scan worker sonucu JSON object olmalıdır."
        )

    shard_id = result.get("shard_id")

    if not isinstance(shard_id, str) or not shard_id:
        raise ValueError(
            "Full scan worker sonucunda geçerli "
            "shard_id bulunmalıdır."
        )

    mode = result.get("mode")

    if mode != "full_repository_scan":
        raise ValueError(
            f"{shard_id} sonucu full_repository_scan "
            "modunda değildir."
        )

    findings = result.get("findings")

    if not isinstance(findings, list):
        raise ValueError(
            f"{shard_id} sonucunda findings listesi yok."
        )

    failed_units = result.get("failed_units")

    if not isinstance(failed_units, list):
        raise ValueError(
            f"{shard_id} sonucunda failed_units listesi yok."
        )

    stats = result.get("stats")

    if not isinstance(stats, dict):
        raise ValueError(
            f"{shard_id} sonucunda stats object yok."
        )

    return result


def _finding_key(
    finding: dict[str, Any],
) -> tuple[Any, ...]:
    return (
        finding.get("file"),
        finding.get("line"),
        finding.get("severity"),
        finding.get("category"),
        finding.get("message"),
    )


def _deduplicate_findings(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduplicated = []
    seen = set()

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        key = _finding_key(finding)

        if key in seen:
            continue

        seen.add(key)
        deduplicated.append(finding)

    return deduplicated


def _deduplicate_failed_units(
    failed_units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduplicated = []
    seen = set()

    for failed_unit in failed_units:
        if not isinstance(failed_unit, dict):
            continue

        key = (
            failed_unit.get("unit_id"),
            failed_unit.get("affected_files"),
            failed_unit.get("summary"),
        )

        if key in seen:
            continue

        seen.add(key)
        deduplicated.append(failed_unit)

    return deduplicated


def merge_full_scan_worker_results(
    result_paths: list[str],
    expected_shard_ids: list[str],
) -> dict[str, Any]:
    """
    Full-scan worker artifact'lerini doğrular ve deterministik birleştirir.

    Eksik, tekrar eden veya beklenmeyen shard sonuçları kabul edilmez.
    """
    expected = sorted(set(expected_shard_ids))

    if len(expected) != len(expected_shard_ids):
        raise ValueError(
            "Beklenen full scan shard listesinde "
            "aynı shard_id birden fazla kez bulunuyor."
        )

    results_by_shard: dict[str, dict[str, Any]] = {}

    for result_path in result_paths:
        result = _load_worker_result(result_path)
        shard_id = result["shard_id"]

        if shard_id in results_by_shard:
            raise ValueError(
                f"{shard_id} için birden fazla "
                "full scan worker sonucu bulundu."
            )

        results_by_shard[shard_id] = result

    actual = sorted(results_by_shard)

    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))

    if missing:
        raise ValueError(
            "Full scan worker sonuçlarında eksik shard var: "
            + ", ".join(missing)
        )

    if unexpected:
        raise ValueError(
            "Beklenmeyen full scan worker shard sonucu var: "
            + ", ".join(unexpected)
        )

    findings: list[dict[str, Any]] = []
    failed_units: list[dict[str, Any]] = []

    merged_stats = {
        key: 0
        for key in FULL_SCAN_STAT_KEYS
    }

    for shard_id in expected:
        result = results_by_shard[shard_id]

        findings.extend(result["findings"])
        failed_units.extend(result["failed_units"])

        stats = result["stats"]

        for key in FULL_SCAN_STAT_KEYS:
            value = stats.get(key, 0)

            if not isinstance(value, int):
                raise ValueError(
                    f"{shard_id} stats.{key} integer olmalıdır."
                )

            merged_stats[key] += value

    return {
        "completed_shards": expected,
        "findings": _deduplicate_findings(findings),
        "failed_units": _deduplicate_failed_units(
            failed_units
        ),
        "stats": merged_stats,
    }
