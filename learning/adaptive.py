"""Validated result ledger and time-filtered rolling team features."""

from datetime import UTC, datetime, timedelta

from learning.adaptive import timestamp
from prediction.engine import TeamForm


RESULT_CONFLICT_FIELDS = (
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
)


def validate_result(row: dict) -> dict:
    """Validate and normalize a settled match result."""
    r = dict(row)

    for name in ("fixture_id", "home_team", "away_team", "kickoff"):
        if not r.get(name):
            raise ValueError(f"Missing {name}")

    if r["home_team"] == r["away_team"]:
        raise ValueError("Teams must differ")

    start = timestamp(r["kickoff"])

    for name in ("home_goals", "away_goals"):
        if name not in r:
            raise ValueError(f"Missing {name}")

        value = r[name]

        if isinstance(value, bool):
            raise ValueError(f"Invalid {name}")

        try:
            integer_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {name}") from exc

        if str(value).strip() != str(integer_value):
            raise ValueError(f"Invalid {name}")

        if not 0 <= integer_value <= 30:
            raise ValueError(f"Invalid {name}")

        r[name] = integer_value

    r.setdefault(
        "available_at",
        (start + timedelta(hours=3)).isoformat(),
    )

    if timestamp(r["available_at"]) <= start:
        raise ValueError("Result cannot be available before kickoff")

    r["fixture_id"] = str(r["fixture_id"])

    return r


def _conflict_signature(existing: dict, incoming: dict) -> dict:
    """Build a stable representation of a provider correction."""
    changed_fields = [
        name
        for name in RESULT_CONFLICT_FIELDS
        if existing.get(name) != incoming.get(name)
    ]

    return {
        "fixture_id": incoming["fixture_id"],
        "existing": {
            name: existing.get(name)
            for name in RESULT_CONFLICT_FIELDS
        },
        "incoming": {
            name: incoming.get(name)
            for name in RESULT_CONFLICT_FIELDS
        },
        "changed_fields": changed_fields,
    }


def _conflict_already_recorded(conflicts: list, signature: dict) -> bool:
    """Avoid writing the same provider conflict on every workflow run."""
    return any(
        str(conflict.get("fixture_id")) == str(signature["fixture_id"])
        and conflict.get("existing") == signature["existing"]
        and conflict.get("incoming") == signature["incoming"]
        for conflict in conflicts
    )


def merge_results(
    existing: list,
    incoming: list,
    conflicts: list | None = None,
) -> list:
    """Merge provider results without letting one correction stop the system.

    Existing settled results remain authoritative.

    If the provider later changes a team name or score for an already stored
    fixture, the original stored result is preserved and the disagreement is
    written to the optional ``conflicts`` ledger.

    This prevents one historical provider correction from blocking:
    - new result ingestion,
    - new predictions,
    - performance evaluation,
    - adaptive learning.

    Duplicate conflict entries are not created on later workflow runs.
    """
    indexed: dict[str, dict] = {}

    for row in existing:
        validated = validate_result(row)
        indexed[validated["fixture_id"]] = validated

    for row in incoming:
        result = validate_result(row)
        fixture_id = result["fixture_id"]

        old = indexed.get(fixture_id)

        if old is None:
            indexed[fixture_id] = result
            continue

        signature = _conflict_signature(old, result)

        if not signature["changed_fields"]:
            # Same settled fact. Keep the already persisted version.
            continue

        if conflicts is not None and not _conflict_already_recorded(
            conflicts,
            signature,
        ):
            conflicts.append(
                {
                    **signature,
                    "detected_at": datetime.now(UTC).isoformat(),
                    "status": "unresolved",
                    "resolution": None,
                }
            )

        # Never silently overwrite a settled historical fact.
        # The conflict can later be reviewed/resolved independently.
        continue

    return sorted(
        indexed.values(),
        key=lambda r: (
            timestamp(r["kickoff"]),
            r["fixture_id"],
        ),
    )


def forms(
    results: list,
    home: str,
    away: str,
    cutoff,
) -> tuple:
    """Build rolling pre-match team form without future-data leakage."""
    prior = sorted(
        (
            r
            for r in results
            if timestamp(r["available_at"]) < cutoff
        ),
        key=lambda r: (
            timestamp(r["kickoff"]),
            str(r["fixture_id"]),
        ),
    )

    ratings: dict[str, float] = {}
    histories: dict[str, list[tuple[int, int]]] = {}

    for r in prior:
        h = r["home_team"]
        a = r["away_team"]

        hg = r["home_goals"]
        ag = r["away_goals"]

        rh = ratings.get(h, 1500.0)
        ra = ratings.get(a, 1500.0)

        expected = 1 / (1 + 10 ** ((ra - rh - 65) / 400))

        actual = (
            1.0
            if hg > ag
            else 0.0
            if hg < ag
            else 0.5
        )

        delta = 20 * (actual - expected)

        ratings[h] = rh + delta
        ratings[a] = ra - delta

        histories.setdefault(h, []).append((hg, ag))
        histories.setdefault(a, []).append((ag, hg))

    def team(name: str) -> TeamForm:
        rows = histories.get(name, [])[-10:]
        n = len(rows)

        if not n:
            return TeamForm(
                1.35,
                1.35,
                1.0,
                0,
                elo=ratings.get(name, 1500.0),
            )

        goals_for = sum(
            scored
            for scored, _ in rows
        ) / n

        goals_against = sum(
            conceded
            for _, conceded in rows
        ) / n

        points_per_game = sum(
            3
            if scored > conceded
            else 1
            if scored == conceded
            else 0
            for scored, conceded in rows
        ) / n

        return TeamForm(
            goals_for,
            goals_against,
            points_per_game,
            n,
            elo=ratings.get(name, 1500.0),
        )

    return team(home), team(away)
