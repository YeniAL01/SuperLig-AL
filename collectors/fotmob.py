"""Conservative adapter: unknown provider schemas fail explicitly."""
from datetime import UTC, datetime
import re
from app.models import Fixture
from collectors.http import HttpClient

class FotMobCollector:
    BASE_URL = "https://www.fotmob.com/api/data"

    def __init__(self, client=None):
        self.client = client or HttpClient()
        self._league_cache = {}

    def _matches(self, league_id):
        if league_id not in self._league_cache:
            data = self.client.get_json(f"{self.BASE_URL}/leagues", {"id": league_id})
            rows = data.get("fixtures", {}).get("allMatches")
            if rows is None:
                rows = data.get("matches", {}).get("allMatches")
            if not isinstance(rows, list):
                raise ValueError("Unsupported FotMob league schema")
            self._league_cache[league_id] = rows
        return self._league_cache[league_id]

    def fixtures(self, league_id):
        fixtures = []
        for m in self._matches(league_id):
            status = m.get("status", {})
            if status.get("finished") or status.get("cancelled"):
                continue
            if not status.get("utcTime"):
                continue
            start = datetime.fromisoformat(status["utcTime"].replace("Z", "+00:00"))
            if start > datetime.now(UTC) and m.get("home", {}).get("name") and m.get("away", {}).get("name"):
                fixtures.append(Fixture(int(m["id"]), m["home"]["name"], m["away"]["name"], start))
        return fixtures

    def results(self, league_id):
        rows = []
        observed = datetime.now(UTC).isoformat()
        for m in self._matches(league_id):
            status = m.get("status", {})
            if not status.get("finished") or status.get("cancelled") or not status.get("utcTime"):
                continue
            h, a = m.get("home", {}), m.get("away", {})
            hs, aws = h.get("score"), a.get("score")
            if hs is None or aws is None:
                # Observed league endpoint encodes full-time score in status.scoreStr.
                score = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", status.get("scoreStr", ""))
                if score is None or status.get("awarded"):
                    continue
                hs, aws = map(int, score.groups())
            if not h.get("name") or not a.get("name"):
                continue
            rows.append({"fixture_id": str(m["id"]), "home_team": h["name"], "away_team": a["name"],
                         "kickoff": status["utcTime"], "home_goals": hs, "away_goals": aws,
                         "available_at": observed, "source": "fotmob"})
        return rows

    def match(self, fixture_id):
        return self.client.get_json(f"{self.BASE_URL}/matchDetails", {"matchId": fixture_id})

