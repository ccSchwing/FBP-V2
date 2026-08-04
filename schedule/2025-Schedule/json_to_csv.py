import argparse
import csv
import json
from pathlib import Path


DEFAULT_COLUMNS = [
    "GameId",
    "Week",
    "Date",
    "Away",
    "Home",
    "AwayScore",
    "HomeScore",
    "Spread",
    "Winner",
    "Underdog",
]


def flatten_value(value):
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value.values()))
    return value


def flatten_item(item):
    return {key: flatten_value(value) for key, value in item.items()}


def convert_json_to_csv(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as source:
        payload = json.load(source)

    items = payload.get("Items", [])
    rows = [flatten_item(item) for item in items]

    if not rows:
        raise ValueError(f"No items found in {input_path}")

    fieldnames = [column for column in DEFAULT_COLUMNS if column in rows[0]]
    rows = [{column: row.get(column, "") for column in fieldnames} for row in rows]

    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert schedule JSON to CSV")
    parser.add_argument(
        "input",
        nargs="?",
        default="2025-schedule-data.json",
        help="Path to the JSON file",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="debug-2025-Schedule.csv",
        help="Path to the CSV file",
    )
    args = parser.parse_args()

    convert_json_to_csv(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()