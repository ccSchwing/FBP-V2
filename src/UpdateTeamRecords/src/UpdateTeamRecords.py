import json
import os
import logging
from collections import defaultdict
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from aws_lambda_powertools import Tracer
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig

from fbplib.decimalDefault import decimal_default
from fbplib.getCurrentWeek import getCurrentWeek

tracer = Tracer()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,
    allow_credentials=False,
)

app = APIGatewayHttpResolver(cors=cors_config)


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@tracer.capture_method
@app.get(r"/updateTeamRecords")
def updateTeamRecords() -> Response:
    logger.info("Fetching team records")
    try:
        dynamodb = boto3.resource("dynamodb")
        record_table = dynamodb.Table(os.environ["FBPTeamRecordsTableName"])
        schedule_table = dynamodb.Table(os.environ["FBPScheduleTableName"])

        current_week = getCurrentWeek() or 1
        completed_week = max(0, int(current_week) - 1)
        query_params = app.current_event.query_string_parameters or {}
        include_diagnostics = _as_bool(query_params.get("diagnostics", "true"))

        weeks_response = schedule_table.scan(
            FilterExpression=Attr("Week").between(1, completed_week)
        )
        items = weeks_response.get("Items", [])

        while "LastEvaluatedKey" in weeks_response:
            weeks_response = schedule_table.scan(
                FilterExpression=Attr("Week").between(1, completed_week),
                ExclusiveStartKey=weeks_response["LastEvaluatedKey"],
            )
            items.extend(weeks_response.get("Items", []))

        items.sort(key=lambda x: x.get("Week", 0))

        # Recompute role-based records from scratch so each run is deterministic.
        team_records_totals = defaultdict(
            lambda: {
                "UnderdogWins": Decimal(0),
                "FavoriteWins": Decimal(0),
                "UnderdogLosses": Decimal(0),
                "FavoriteLosses": Decimal(0),
            }
        )
        for item in items:
            underdog = str(item.get("Underdog", "")).strip()
            winner = str(item.get("Winner", "")).strip()
            home_team = item.get("Home")
            away_team = item.get("Away")

            # Ignore unplayed/placeholder games until they have H/A markers.
            if winner not in {"H", "A"} or underdog not in {"H", "A"}:
                continue

            winning_team = home_team if winner == "H" else away_team
            losing_team = away_team if winner == "H" else home_team

            winner_role = "Underdog" if winner == underdog else "Favorite"
            loser_role = "Favorite" if winner_role == "Underdog" else "Underdog"

            if winning_team:
                team_records_totals[winning_team][f"{winner_role}Wins"] += Decimal(1)
            if losing_team:
                team_records_totals[losing_team][f"{loser_role}Losses"] += Decimal(1)

        valid_games = 0
        for team_total in team_records_totals.values():
            valid_games += int(team_total["UnderdogWins"] + team_total["FavoriteWins"])

        # Build the complete team set from both existing records and schedule rows.
        records_response = record_table.scan()
        team_records = records_response.get("Items", [])
        while "LastEvaluatedKey" in records_response:
            records_response = record_table.scan(
                ExclusiveStartKey=records_response["LastEvaluatedKey"]
            )
            team_records.extend(records_response.get("Items", []))

        team_names = set()
        for item in items:
            if item.get("Home"):
                team_names.add(item["Home"])
            if item.get("Away"):
                team_names.add(item["Away"])
        for team_record in team_records:
            if team_record.get("TeamName"):
                team_names.add(team_record["TeamName"])

        for team_name in sorted(team_names):
            totals = team_records_totals.get(
                team_name,
                {
                    "UnderdogWins": Decimal(0),
                    "FavoriteWins": Decimal(0),
                    "UnderdogLosses": Decimal(0),
                    "FavoriteLosses": Decimal(0),
                },
            )
            games_played = (
                totals["UnderdogWins"]
                + totals["FavoriteWins"]
                + totals["UnderdogLosses"]
                + totals["FavoriteLosses"]
            )
            record_table.update_item(
                Key={"TeamName": team_name},
                UpdateExpression=(
                    "SET UnderdogWins = :uw, FavoriteWins = :fw, "
                    "UnderdogLosses = :ul, FavoriteLosses = :fl, GamesPlayed = :gp"
                ),
                ExpressionAttributeValues={
                    ":uw": totals["UnderdogWins"],
                    ":fw": totals["FavoriteWins"],
                    ":ul": totals["UnderdogLosses"],
                    ":fl": totals["FavoriteLosses"],
                    ":gp": games_played,
                },
            )

        diagnostics = {
            "currentWeek": int(current_week),
            "completedWeek": int(completed_week),
            "scheduleItemsScanned": len(items),
            "validGamesCounted": valid_games,
            "teamsUpdated": len(team_names),
            "aggregate": {
                "UnderdogWins": int(sum(v["UnderdogWins"] for v in team_records_totals.values())),
                "FavoriteWins": int(sum(v["FavoriteWins"] for v in team_records_totals.values())),
                "UnderdogLosses": int(sum(v["UnderdogLosses"] for v in team_records_totals.values())),
                "FavoriteLosses": int(sum(v["FavoriteLosses"] for v in team_records_totals.values())),
            },
        }

        return Response(
            body=json.dumps(
                {"diagnostics": diagnostics}
                if include_diagnostics
                else items,
                default=decimal_default,
            ),
            status_code=200,
            headers={"Content-Type": "application/json"},
        )
    except ClientError as e:
        error_message = e.response.get("Error", {}).get("Message", str(e))
        logger.error(f"Error fetching team records: {error_message}")
        return Response(
            body=json.dumps({"error": "Could not fetch team records"}),
            status_code=500,
            headers={"Content-Type": "application/json"},
        )


@tracer.capture_lambda_handler
def lambda_handler(event, context):
    return app.resolve(event, context)