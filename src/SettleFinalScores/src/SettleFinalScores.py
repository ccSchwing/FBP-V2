"""
settle_spreads_lambda.py - fill final scores and ATS Winner into the frozen weekly schedule CSV.

CORRECTION: Winner = ATS Cover (not game winner)
------------------------------------------------
Your CSV has:
  - Spread: unsigned magnitude (3.5)
  - Underdog: 'H' or 'A' indicating which team received the points
  - Winner: must be calculated AFTER scores arrive to determine who COVERED

Since spreads have half-points (3.5, 7.5, etc.), there are no pushes -
someone always wins ATS.

ATS GRADING LOGIC:
  If Underdog = 'H' (home got the points):
      Home covers if (HomeScore + Spread) > AwayScore
      Away covers if (HomeScore + Spread) < AwayScore
  
  If Underdog = 'A' (away got the points):
      Away covers if (AwayScore + Spread) > HomeScore
      Home covers if (AwayScore + Spread) < HomeScore

DESIGN PRINCIPLE: PATCH, DON'T REGENERATE
-----------------------------------------
This Lambda reads the existing week{N}-Schedule.csv from S3, fills in
AwayScore / HomeScore / Winner, and writes it back to the SAME key.

It never recomputes Spread or Underdog. Those were frozen at poll time and must
never move - that is the point of the one-poll-per-week policy.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from datetime import datetime, timezone

import boto3

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)
app = APIGatewayHttpResolver(cors=cors_config)

# ── Constants ────────────────────────────────────────────────────────────────

ENDZONE_URL = "https://mcp.endzoneapi.com/v1/get_games"
ENDZONE_COST = 5                       # credits per call
SECRET_NAME = os.environ.get('EndzoneApiSecretName')

S3_BUCKET = os.environ.get('S3BucketName', 'my-fbp.com')
YEAR = os.environ.get('Year', '2026')

SEASON = int(os.environ.get('Year', '2026'))
KICKOFF_TOLERANCE_MINUTES = 120

REQUIRED_COLUMNS = {
    'GameId', 'Week', 'Date', 'Away', 'Home',
    'AwayScore', 'HomeScore', 'Spread', 'Winner', 'Underdog',
}


# ── Team short name -> EndzoneAPI code ───────────────────────────────────────

# *** ORIGINAL: This was your SHORT_TO_CODE table unchanged
SHORT_TO_CODE = {
    # AFC East
    "Bills": "BUF", "Dolphins": "MIA", "Patriots": "NE", "Jets": "NYJ",
    # AFC North
    "Ravens": "BAL", "Bengals": "CIN", "Browns": "CLE", "Steelers": "PIT",
    # AFC South
    "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Titans": "TEN",
    # AFC West
    "Broncos": "DEN", "Chiefs": "KC", "Raiders": "LV", "Chargers": "LAC",
    # NFC East
    "Cowboys": "DAL", "Giants": "NYG", "Eagles": "PHI", "Commanders": "WAS",
    # NFC North
    "Bears": "CHI", "Lions": "DET", "Packers": "GB", "Vikings": "MIN",
    # NFC South
    "Falcons": "ATL", "Panthers": "CAR", "Saints": "NO", "Buccaneers": "TB",
    # NFC West
    "Cardinals": "ARI", "Rams": "LAR", "49ers": "SF", "Seahawks": "SEA",
}

# *** ADDED: Provider-specific / historical codes -> modern official abbreviation.
#     This handles the EndzoneAPI/GGIS scheme which uses different codes than 
#     the official abbreviations you have in SHORT_TO_CODE. Most importantly:
#     "LA" is NOT a generic "Los Angeles" marker - it's the Rams' dedicated GSIS code.
#     The Chargers have their own distinct code ("LAC"), so this is unambiguous.
PROVIDER_CODE_ALIASES = {
    # GSIS scheme differences (nflgsis.com club codes)
    "LA":  "LAR",   # <<< FIXED YOUR ISSUE: "LA" from EndzoneAPI -> "LAR" (Rams)
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "WSH": "WAS",

    # Historical codes for archival support (2026 won't use these)
    "STL": "LAR",   # Rams, St. Louis era
    "SD":  "LAC",   # Chargers, San Diego era
    "OAK": "LV",    # Raiders, Oakland era
}

# *** ADDED: Guard rails evaluated once at import. Detects typos in the alias table
#     that would cause silent "unresolved game" errors later.
_OFFICIAL_CODES = frozenset(SHORT_TO_CODE.values())

_shadowed = set(PROVIDER_CODE_ALIASES) & _OFFICIAL_CODES
if _shadowed:
    raise RuntimeError(
        f"alias table shadows official code(s): {sorted(_shadowed)}")

_dangling = set(PROVIDER_CODE_ALIASES.values()) - _OFFICIAL_CODES
if _dangling:
    raise RuntimeError(
        f"alias table targets unknown code(s): {sorted(_dangling)}")


class UnknownTeam(ValueError):
    """Raised when a short team name cannot be mapped to an EndzoneAPI code."""


def team_code(short_name: str) -> str:
    """
    *** UPDATED: Map team name to an EndzoneAPI 3-letter code.
    
    Handles, in order:
        1. an official code already        ("LAR", "lv")
        2. a provider-specific code        ("LA" -> LAR)  <<< NEW PATH
        3. a short nickname from the CSV   ("Rams")
        4. a full team name                ("Los Angeles Rams")  <<< NEW PATH
    
    Args:
        short_name: Any team spelling (CSV nickname, GSIS code, or full name)
    
    Returns:
        Standardized 3-letter official abbreviation (e.g., "LAR", "LAC")
    
    Raises:
        UnknownTeam: If the name cannot be mapped
    """
    if not short_name:
        raise UnknownTeam("empty team name")
    cleaned = short_name.strip()
    upper = cleaned.upper()
    
    # *** NEW: Check if already an official code (case-insensitive)
    if upper in _OFFICIAL_CODES:
        return upper
    
    # *** NEW: Check if it's a provider-specific code (e.g., "LA" for Rams)
    if upper in PROVIDER_CODE_ALIASES:
        return PROVIDER_CODE_ALIASES[upper]
    
    # *** ORIGINAL: Your existing check for nickname
    if cleaned in SHORT_TO_CODE:
        return SHORT_TO_CODE[cleaned]
    
    # *** NEW: Try to extract nickname from full team name
    nickname = cleaned.split()[-1]
    if nickname in SHORT_TO_CODE:
        return SHORT_TO_CODE[nickname]
    
    raise UnknownTeam(f"cannot map team name {short_name!r} to a code")


# ── Errors ───────────────────────────────────────────────────────────────────

class SettlementError(RuntimeError):
    """Raised when settlement cannot complete."""


# ── Secrets / config ─────────────────────────────────────────────────────────



def get_endzone_api_key() -> str:
    """*** UNCHANGED: Your original implementation."""
    if not SECRET_NAME:
        raise SettlementError("EndzoneApiSecretName environment variable is not set")
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=SECRET_NAME)
    return response['SecretString']


# ── S3 ───────────────────────────────────────────────────────────────────────

def schedule_key(week: int) -> str:
    """*** UNCHANGED: Same key layout your GenerateSpreads Lambda writes to."""
    return f"schedule/{YEAR}-Schedule/week{week}-Schedule.csv"


def read_csv_from_s3(bucket: str, key: str) -> tuple[list[dict], list[str]]:
    """*** UNCHANGED: Read the frozen schedule CSV. Returns (rows, fieldnames)."""
    s3 = boto3.client('s3')
    try:
        body = s3.get_object(Bucket=bucket, Key=key)['Body'].read()
    except Exception as exc:
        raise SettlementError(f"could not read s3://{bucket}/{key}: {exc}") from exc

    text = body.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or [])

    missing = REQUIRED_COLUMNS - set(fieldnames)
    if missing:
        raise SettlementError(
            f"{key} is missing expected column(s): {sorted(missing)}")

    return list(reader), fieldnames


def write_csv_to_s3(bucket: str, key: str, rows: list[dict],
                    fieldnames: list[str]) -> int:
    """*** UNCHANGED: Overwrite the CSV in place. Returns byte count written."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    payload = buf.getvalue().encode('utf-8')

    boto3.client('s3').put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType='text/csv',
        Metadata={'source': 'endzone-settlement'},
    )
    return len(payload)


# ── EndzoneAPI ───────────────────────────────────────────────────────────────

def fetch_week_games(api_key: str, week: int, *, season: int = SEASON,
                     timeout: int = 60, max_retries: int = 3) -> list[dict]:
    """*** MINIMAL CHANGE: You added 'data' wrapper handling."""
    body = json.dumps({'season': season, 'week': week}).encode('utf-8')
    request = urllib.request.Request(
        ENDZONE_URL,
        data=body,
        headers={'Content-Type': 'application/json',
                 'Accept': 'application/json',
                 'x-api-key': api_key},
        method='POST',
    )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
            # *** YOUR CHANGE: Handle the 'data' wrapper in the response
            data = payload.get('data')
            games = data.get('games') if isinstance(data, dict) else None
            if not isinstance(games, list):
                raise SettlementError(
                    f"unexpected payload: 'games' is {type(games).__name__}")
            return games

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')[:500]
            err = SettlementError(f"HTTP {exc.code} {exc.reason} - {detail}")
            if exc.code != 429 and 400 <= exc.code < 500:
                raise err from exc
            last_error = err

        except (urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as exc:
            last_error = SettlementError(f"{type(exc).__name__}: {exc}")

        if attempt < max_retries:
            delay = min(2.0 ** attempt, 30.0)
            print(f"  attempt {attempt} failed ({last_error}); "
                  f"retrying in {delay:.0f}s", file=sys.stderr)
            time.sleep(delay)

    assert last_error is not None
    raise last_error


def parse_iso(value: str) -> datetime:
    """*** UNCHANGED: Parse ISO timestamp."""
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


# ── ATS Grading Logic ────────────────────────────────────────────────────────

def ats_winner(away_score: int, home_score: int, spread: float,
               underdog: str) -> str:
    """*** UNCHANGED: Your original implementation."""
    """
    Determine ATS winner given final scores and frozen spread info.
    
    Args:
        away_score: Final away team score
        home_score: Final home team score  
        spread: Unsigned spread magnitude (e.g., 3.5)
        underdog: 'H' (home got points) or 'A' (away got points)
    
    Returns:
        'H' if home covered, 'A' if away covered
    
    Since spreads have half-points, there are no pushes.
    """
    if underdog not in ('H', 'A'):
        raise ValueError(f"Invalid underdog value: {underdog!r}")
    
    if underdog == 'H':
        # Home received the points
        # Home covers if (home_score + spread) > away_score
        adjusted_home = home_score + spread
        if adjusted_home > away_score:
            return 'H'
        else:
            return 'A'
    else:
        # Away received the points
        # Away covers if (away_score + spread) > home_score
        adjusted_away = away_score + spread
        if adjusted_away > home_score:
            return 'A'
        else:
            return 'H'


# ── Settlement ───────────────────────────────────────────────────────────────

def settle_rows(rows: list[dict], score_games: list[dict],
                week: int) -> tuple[list[dict], list[str], list[str]]:
    """*** UNCHANGED: Your original implementation."""
    """
    Fill AwayScore / HomeScore / Winner in place.
    
    Returns (updated_rows, problems, unresolved_game_ids).
    Spread, Underdog, and all other fields are left exactly as read.
    """
    problems: list[str] = []

    # Index EndzoneAPI games by (week, away_code, home_code).
    index: dict[tuple[int, str, str], dict] = {}
    for game in score_games:
        try:
            key = (int(game['week']),
                   team_code(game['away_team']),
                   team_code(game['home_team']))
        except (KeyError, UnknownTeam, TypeError, ValueError) as exc:
            problems.append(
                f"score row {game.get('game_id', '?')}: could not index ({exc})")
            continue
        if key in index:
            problems.append(f"duplicate score row for {key[1]}@{key[2]}")
        index[key] = game

    matched: set[tuple[int, str, str]] = set()
    unresolved: list[str] = []

    for row in rows:
        game_id = row.get('GameId', '?')
        away_short = (row.get('Away') or '').strip()
        home_short = (row.get('Home') or '').strip()

        try:
            away_code = team_code(away_short)
            home_code = team_code(home_short)
        except UnknownTeam as exc:
            problems.append(f"{game_id}: {exc}")
            unresolved.append(game_id)
            continue

        key = (week, away_code, home_code)
        score = index.get(key)
        if score is None:
            problems.append(
                f"{game_id}: no EndzoneAPI game for {away_code}@{home_code}")
            unresolved.append(game_id)
            continue
        matched.add(key)

        status = (score.get('status') or '').upper()
        away_score_raw = score.get('away_score')
        home_score_raw = score.get('home_score')

        if status != 'FINAL' or away_score_raw is None or home_score_raw is None:
            problems.append(
                f"{game_id}: not final ({away_code}@{home_code} "
                f"status={status or '?'} {away_score_raw}-{home_score_raw})")
            unresolved.append(game_id)
            continue

        away_score = int(away_score_raw)
        home_score = int(home_score_raw)

        # Parse frozen spread
        spread_str = row.get('Spread', '')
        underdog = (row.get('Underdog') or '').strip()
        
        if spread_str == '' or underdog not in ('H', 'A'):
            problems.append(
                f"{game_id}: missing Spread or Underdog value - cannot grade")
            unresolved.append(game_id)
            continue

        try:
            spread = float(spread_str)
        except ValueError:
            problems.append(
                f"{game_id}: invalid Spread value {spread_str!r}")
            unresolved.append(game_id)
            continue

        # Grade ATS cover
        winner = ats_winner(away_score, home_score, spread, underdog)

        # Patch the row
        row['AwayScore'] = str(away_score)
        row['HomeScore'] = str(home_score)
        row['Winner'] = winner

    # EndzoneAPI games with no corresponding CSV row
    for key in sorted(set(index) - matched):
        problems.append(f"orphan score {key[1]}@{key[2]}: no CSV row")

    return rows, problems, unresolved


# ── Handler ──────────────────────────────────────────────────────────────────
@app.get("/settleFinalScores")
def lambda_handler(event: dict, context) -> dict:
    """*** UNCHANGED: Your original handler implementation."""
    """Plain Lambda handler - invoke from EventBridge, Step Functions, or manually."""
    print(f"Event: {json.dumps(event)}")

    week=0
    dry_run = False
    allow_partial = False
    if 'body' in event:
        week = json.loads(event['body']).get('week')
        dry_run = json.loads(event['body']).get('dry_run', False)
        allow_partial = json.loads(event['body']).get('allow_partial', False)
    if not week or week == 0:
        return {'statusCode': 400,
                'body': json.dumps({'error': 'week is required'})}
    week = int(week)
    if not 1 <= week <= 18:
        return {'statusCode': 400,
                'body': json.dumps({'error': f'invalid week: {week}'})}

    key = schedule_key(week)

    print(f"Settling week {week}: s3://{S3_BUCKET}/{key}")

    try:
        # 1. Read the frozen CSV
        rows, fieldnames = read_csv_from_s3(S3_BUCKET, key)
        print(f"  read {len(rows)} row(s)")

        already = sum(1 for r in rows
                      if str(r.get('AwayScore', '')).strip() not in ('', '0')
                      or str(r.get('HomeScore', '')).strip() not in ('', '0'))
        if already:
            print(f"  note: {already} row(s) already carry non-zero scores")

        # 2. Fetch final scores
        api_key_json = get_endzone_api_key()
        api_key = json.loads(api_key_json)['fbp/the-endzone-api']
        score_games = fetch_week_games(api_key, week)
        finals = sum(1 for g in score_games
                     if (g.get('status') or '').upper() == 'FINAL')
        print(f"  endzone: {len(score_games)} game(s), {finals} final "
              f"(cost {ENDZONE_COST} credits)")

        # 3. Patch the rows (grades ATS winner based on frozen Spread/Underdog)
        rows, problems, unresolved = settle_rows(rows, score_games, week)
        print(f"  resolved {len(rows) - len(unresolved)}/{len(rows)} row(s)")

        for problem in problems:
            print(f"  PROBLEM {problem}", file=sys.stderr)

        if unresolved and not allow_partial:
            print(f"  refusing to write: {len(unresolved)} unresolved row(s)",
                  file=sys.stderr)
            return {
                'statusCode': 409,
                'body': json.dumps({
                    'week': week,
                    'error': 'incomplete settlement',
                    'unresolved': unresolved,
                    'problems': problems,
                    'hint': 'pass allow_partial=true to write anyway',
                }),
            }

        if dry_run:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'week': week,
                    'dry_run': True,
                    'resolved': len(rows) - len(unresolved),
                    'unresolved': unresolved,
                    'problems': problems,
                }),
            }

        # 4. Overwrite the same key
        written = write_csv_to_s3(S3_BUCKET, key, rows, fieldnames)
        print(f"  wrote {written} bytes to s3://{S3_BUCKET}/{key}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'week': week,
                's3Key': key,
                'rows': len(rows),
                'resolved': len(rows) - len(unresolved),
                'unresolved': unresolved,
                'bytesWritten': written,
                'problems': problems,
            }),
        }

    except SettlementError as exc:
        print(f"Settlement failed: {exc}", file=sys.stderr)
        return {'statusCode': 502,
                'body': json.dumps({'error': str(exc)})}

    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return {'statusCode': 500,
                'body': json.dumps({'error': f'unexpected: {exc}'})}
