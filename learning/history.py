"""Validated result ledger and time-filtered rolling team features."""
from datetime import UTC, datetime, timedelta
from learning.adaptive import timestamp
from prediction.engine import TeamForm


def validate_result(row: dict) -> dict:
    r = dict(row)
    for name in ("fixture_id", "home_team", "away_team", "kickoff"):
        if not r.get(name):
            raise ValueError(f"Missing {name}")
    if r["home_team"] == r["away_team"]:
        raise ValueError("Teams must differ")
    start = timestamp(r["kickoff"])
    for name in ("home_goals", "away_goals"):
        value = r[name]
        if isinstance(value, bool) or str(value).strip() != str(int(value)) or not 0 <= int(value) <= 30:
            raise ValueError(f"Invalid {name}")
        r[name] = int(value)
    r.setdefault("available_at", (start + timedelta(hours=3)).isoformat())
    if timestamp(r["available_at"]) <= start:
        raise ValueError("Result cannot be available before kickoff")
    r["fixture_id"] = str(r["fixture_id"])
    return r


def merge_results(existing: list, incoming: list, conflicts: list | None = None) -> list:
    """Merge new results without allowing a provider correction to stop the run.

    Existing settled facts remain authoritative. A conflicting provider row is
    appended to ``conflicts`` when supplied, so it can be reviewed separately.
    """
    indexed = {str(r["fixture_id"]): validate_result(r) for r in existing}
    for row in incoming:
        r = validate_result(row)
        old = indexed.get(r["fixture_id"])
        if old:
            fields = ("home_team", "away_team", "home_goals", "away_goals")
            changed = [name for name in fields if old[name] != r[name]]
            if changed and conflicts is not None:
                signature = {
                    "fixture_id": r["fixture_id"],
                    "existing": {name: old[name] for name in fields},
                    "incoming": {name: r[name] for name in fields},
                    "changed_fields": changed,
                }
                duplicate = any(
                    c.get("fixture_id") == signature["fixture_id"]
                    and c.get("existing") == signature["existing"]
                    and c.get("incoming") == signature["incoming"]
                    for c in conflicts
                )
                if not duplicate:
                    conflicts.append({**signature, "detected_at": datetime.now(UTC).isoformat()})
            continue
        indexed[r["fixture_id"]] = r
    return sorted(indexed.values(), key=lambda r: (timestamp(r["kickoff"]), r["fixture_id"]))


def forms(results: list, home: str, away: str, cutoff) -> tuple:
    prior = sorted((r for r in results if timestamp(r["available_at"]) < cutoff),
                   key=lambda r: (timestamp(r["kickoff"]), str(r["fixture_id"])))
    ratings, histories = {}, {}
    for r in prior:
        h, a = r["home_team"], r["away_team"]
        hg, ag = r["home_goals"], r["away_goals"]
        rh, ra = ratings.get(h, 1500.), ratings.get(a, 1500.)
        expected = 1/(1+10**((ra-rh-65)/400))
        delta = 20*((1 if hg>ag else 0 if hg<ag else .5)-expected)
        ratings[h], ratings[a] = rh+delta, ra-delta
        histories.setdefault(h, []).append((hg, ag))
        histories.setdefault(a, []).append((ag, hg))
    def team(name):
        rows = histories.get(name, [])[-10:]
        n = len(rows)
        return TeamForm(
            sum(h for h,a in rows)/n if n else 1.35,
            sum(a for h,a in rows)/n if n else 1.35,
            sum(3 if h>a else 1 if h==a else 0 for h,a in rows)/n if n else 1.,
            n, elo=ratings.get(name, 1500.))
    return team(home), team(away)
