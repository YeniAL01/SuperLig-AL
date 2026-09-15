"""FotMob public-endpoint adapter."""
from __future__ import annotations
from datetime import UTC, datetime
from app.models import Fixture
from collectors.http import HttpClient

class FotMobCollector:
    """Collects fixtures and limited team form from FotMob public data."""
    BASE_URL = "https://www.fotmob.com/api"
    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def fixtures(self, league_id: int) -> list[Fixture]:
        """Return future fixtures from the league match index."""
        data = self.client.get_json(f"{self.BASE_URL}/leagues", {"id": league_id})
        matches = data.get("matches", {}).get("allMatches", [])
        result: list[Fixture] = []
        for match in matches:
            status = match.get("status", {})
            utc_time = status.get("utcTime")
            if not utc_time:
                continue
            start = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
            if start > datetime.now(UTC):
                home, away = match.get("home", {}).get("name"), match.get("away", {}).get("name")
                if home and away:
                    result.append(Fixture(int(match["id"]), home, away, start, match.get("venue", "")))
        return result

    def match(self, fixture_id: int) -> dict:
        """Return match detail, including lineups when the provider exposes them."""
        return self.client.get_json(f"{self.BASE_URL}/matchDetails", {"matchId": fixture_id})
