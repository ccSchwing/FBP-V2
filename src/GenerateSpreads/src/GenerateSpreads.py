from __future__ import annotations
import json
import csv
import io
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import boto3
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from datetime import datetime, timezone, date, timedelta
from fbplib.getCurrentWeek import getCurrentWeek


cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)
app = APIGatewayHttpResolver(cors=cors_config)
    
# ── Constants ────────────────────────────────────────────────────────────────
ODDS_API_BASE  = "https://api.the-odds-api.com/v4"
SPORT          = "americanfootball_nfl"
REGION         = "us"
MARKET         = "spreads"
ODDS_FORMAT    = "american"
BOOKMAKER      = "draftkings"
SEASON          = 2026
WEEK1_SUNDAY    = datetime(2026, 9, 13, tzinfo=timezone.utc).date()
LAST_WEEK       = 18

BOUNDARY_HOUR_UTC = 6

S3_BUCKET      = os.environ['S3BucketName']          # 'my-fbp.com'
S3_PREFIX      = os.environ.get('S3Prefix', 'schedules/2026')
SECRET_NAME    = os.environ['OddsApiSecretName']     # 'fbp/odds-api-key'
CONFIG_TABLE   = os.environ['FBPConfigTableName']    # '2026-FBP-Config'

CSV_COLUMNS = [
    'GameId', 'Week', 'Date', 'Away', 'Home',
    'AwayScore', 'HomeScore', 'Spread', 'Winner', 'Underdog'
]

# ── Team Name Lookup ─────────────────────────────────────────────────────────
TEAM_NAMES = {
    # AFC East
    "Buffalo Bills":            "Bills",
    "Miami Dolphins":           "Dolphins",
    "New England Patriots":     "Patriots",
    "New York Jets":            "Jets",
    # AFC North
    "Baltimore Ravens":         "Ravens",
    "Cincinnati Bengals":       "Bengals",
    "Cleveland Browns":         "Browns",
    "Pittsburgh Steelers":      "Steelers",
    # AFC South
    "Houston Texans":           "Texans",
    "Indianapolis Colts":       "Colts",
    "Jacksonville Jaguars":     "Jaguars",
    "Tennessee Titans":         "Titans",
    # AFC West
    "Denver Broncos":           "Broncos",
    "Kansas City Chiefs":       "Chiefs",
    "Las Vegas Raiders":        "Raiders",
    "Los Angeles Chargers":     "Chargers",
    # NFC East
    "Dallas Cowboys":           "Cowboys",
    "New York Giants":          "Giants",
    "Philadelphia Eagles":      "Eagles",
    "Washington Commanders":    "Commanders",
    # NFC North
    "Chicago Bears":            "Bears",
    "Detroit Lions":            "Lions",
    "Green Bay Packers":        "Packers",
    "Minnesota Vikings":        "Vikings",
    # NFC South
    "Atlanta Falcons":          "Falcons",
    "Carolina Panthers":        "Panthers",
    "New Orleans Saints":       "Saints",
    "Tampa Bay Buccaneers":     "Buccaneers",
    # NFC West
    "Arizona Cardinals":        "Cardinals",
    "Los Angeles Rams":         "Rams",
    "San Francisco 49ers":      "49ers",
    "Seattle Seahawks":         "Seahawks",
}

# --------------------------------------------------------------------------- #
# Errors                                                                      #
# --------------------------------------------------------------------------- #

class OddsAPIError(RuntimeError):
    """Raised for any unrecoverable failure talking to The Odds API."""

    def __init__(self, message: str, status: int | None = None,
                 body: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body

# --------------------------------------------------------------------------- #
# Week window helpers (needed by fetch_odds + validate_games)                   #
# --------------------------------------------------------------------------- #

def week_sunday(week: int, season_sunday: date = WEEK1_SUNDAY) -> date:
    """The Sunday of the given week. Used as the anchor for the window."""
    if not 1 <= week <= LAST_WEEK:
        raise ValueError(f"week must be 1..{LAST_WEEK}, got {week}")
    return season_sunday + timedelta(days=7 * (week - 1))


def _boundary(day: date) -> datetime:
    return datetime(day.year, day.month, day.day,
                    BOUNDARY_HOUR_UTC, tzinfo=timezone.utc)


def week_window(week: int,
                season_sunday: date = WEEK1_SUNDAY) -> tuple[datetime, datetime]:
    """Half-open UTC window [from, to) that covers every kickoff in `week`."""
    from datetime import date, timedelta
    sunday = week_sunday(week, season_sunday)
    return (
        _boundary(sunday - timedelta(days=5)),  # Tue 06:00 UTC before Sunday
        _boundary(sunday + timedelta(days=2)),  # Tue 06:00 UTC after Sunday
    )


def iso_z(dt: datetime) -> str:
    """ISO 8601 UTC with a trailing Z, as the API expects."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 string back to a datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))



# ── Helpers ──────────────────────────────────────────────────────────────────
def short_name(full_name: str) -> str:
    """Convert full team name to short name. Raises ValueError if not found."""
    if full_name not in TEAM_NAMES:
        raise ValueError(f"Unknown team name from Odds API: '{full_name}'")
    return TEAM_NAMES[full_name]


def get_api_key() -> str:
    """Retrieve Odds API key from Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=SECRET_NAME)
    return response['SecretString']


def get_current_week() -> int:
    """Read currentWeek from DynamoDB config table."""
    week = getCurrentWeek()
    if isinstance(week, int):
        return week
    raise ValueError(f"Invalid week value: {week}")

# Functions for go here
# --------------------------------------------------------------------------- #
# Core functions                                                              #
# --------------------------------------------------------------------------- #

def fetch_odds(api_key: str, week: int, *, timeout: int = 10,
               max_retries: int = 3,
               backoff_base: float = 2.0) -> tuple[list, dict]:
    """
    Fetch spreads for `week`.

    Returns (games, quota_headers). Raises OddsAPIError on failure.
    """
    lo, hi = week_window(week)
    params = urllib.parse.urlencode({
        "apiKey":           api_key,
        "regions":          REGION,
        "markets":          MARKET,
        "oddsFormat":       ODDS_FORMAT,
        "bookmakers":       BOOKMAKER,
        "commenceTimeFrom": iso_z(lo),
        "commenceTimeTo":   iso_z(hi),
    })
    url = f"{ODDS_API_BASE}/sports/{SPORT}/odds?{params}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                quota = {k.lower(): v for k, v in resp.headers.items()
                         if k.lower().startswith("x-requests-")}
                games = json.loads(resp.read().decode("utf-8"))
                if not isinstance(games, list):
                    raise OddsAPIError(
                        f"unexpected payload type: {type(games).__name__}")
                return games, quota

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            err = OddsAPIError(
                f"HTTP {exc.code} {exc.reason} - {body}", exc.code, body)
            if exc.code != 429 and 400 <= exc.code < 500:
                raise err from exc
            last_error = err

        except (urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as exc:
            last_error = OddsAPIError(f"{type(exc).__name__}: {exc}")

        if attempt < max_retries:
            delay = min(backoff_base ** attempt, 30.0)
            print(f"  attempt {attempt} failed ({last_error}); "
                  f"retrying in {delay:.0f}s", file=sys.stderr)
            time.sleep(delay)

    assert last_error is not None
    raise last_error


def validate_games(games: list, week: int) -> list[str]:
    """
    Sanity-check a response against the requested window.

    Returns a list of human-readable problems; empty means clean.
    """
    lo, hi = week_window(week)
    problems: list[str] = []
    counts: dict[str, int] = {}

    for game in games:
        gid = game.get("id", "<no id>")
        counts[gid] = counts.get(gid, 0) + 1

        raw = game.get("commence_time")
        if not raw:
            problems.append(f"{gid}: missing commence_time")
        else:
            kickoff = parse_iso(raw)
            if not lo <= kickoff < hi:
                problems.append(
                    f"{gid}: kickoff {iso_z(kickoff)} outside window "
                    f"[{iso_z(lo)}, {iso_z(hi)})")

        books = game.get("bookmakers") or []
        matching = [b for b in books if b.get("key") == BOOKMAKER]
        if not matching:
            problems.append(f"{gid}: no {BOOKMAKER} entry")
        elif not any(m.get("key") == MARKET
                     for b in matching for m in (b.get("markets") or [])):
            problems.append(f"{gid}: {BOOKMAKER} has no {MARKET} market")

    for gid, n in counts.items():
        if n > 1:
            problems.append(f"{gid}: appears {n} times")

    return problems

def extract_spread(game: dict, home_full: str, away_full: str, commence: str):
    """
    extract spread and determine underdog from draftkings outcomes.
    raises valueerror if spread is missing or is a pick'em (0).
    returns (spread: float, underdog: str)
    """
    home_spread = None

    for bookmaker in game.get('bookmakers', []):
        for market in bookmaker.get('markets', []):
            if market['key'] == 'spreads':
                for outcome in market.get('outcomes', []):
                    if outcome['name'] == home_full:
                        home_spread = outcome.get('point')
                break
        if home_spread is not None:
            break

    if home_spread is None:
        raise ValueError(
            f"No spread found for game: {away_full} @ {home_full} on {commence}"
        )
    if home_spread == 0:
        raise ValueError(
            f"Pick'em (spread=0) not supported: {away_full} @ {home_full} on {commence}"
        )

    spread   = abs(home_spread)
    underdog = 'H' if home_spread > 0 else 'A'
    return spread, underdog


def build_csv(games: list, week: int) -> str:
    """Convert Odds API game list into CSV string matching import format."""
    rows = []

    for game in games:
        home_full = game['home_team']
        away_full = game['away_team']
        commence  = game['commence_time'][:10]   # YYYY-MM-DD

        # extract_spread uses full names to match outcome['name'] from the API
        spread, underdog = extract_spread(game, home_full, away_full, commence)

        # convert to short names for CSV
        home = short_name(home_full)
        away = short_name(away_full)

        game_num = len(rows) + 1
        rows.append({
            'GameId':    f"W{week}-{game_num:02d}",
            'Week':      week,
            'Date':      commence,
            'Away':      away,
            'Home':      home,
            'AwayScore': 0,
            'HomeScore': 0,
            'Spread':    spread,
            'Winner':    'H or A',
            'Underdog':  underdog,
        })

    if not rows:
        raise ValueError(f"No games returned from Odds API for week {week}")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def write_to_s3(csv_content: str, week: int) -> str:
    """Write CSV to S3 and return the S3 key."""
    Year = os.environ['Year']
    s3_key = f"schedule/{Year}-Schedule/week{week}-Schedule.csv"
    boto3.client('s3').put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=csv_content.encode('utf-8'),
        ContentType='text/csv',
    )
    print(f"Written to s3://{S3_BUCKET}/{s3_key}")
    return s3_key


# ── Handler ──────────────────────────────────────────────────────────────────
@app.get("/generate-spreads")
def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)}")

    week    = get_current_week()
    print(f"Generating spreads for week {week}")

    api_key_json = get_api_key()
    api_key = json.loads(api_key_json)['fbp/odds-api-key']
    games, quota = fetch_odds(api_key, week)
    for problem in validate_games(games, week):
        print(f"Validation problem: {problem}", file=sys.stderr)
        raise OddsAPIError(problem)
    print(f"Odds API returned {len(games)} games")

    csv_content = build_csv(games, week)
    s3_key      = write_to_s3(csv_content, week)

    return {
        'statusCode': 200,
        'week':       week,
        's3Key':      s3_key,
        'gameCount':  csv_content.count('\n') - 1,  # exclude header row
    }
