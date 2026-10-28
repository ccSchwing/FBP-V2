#!/bin/bash

# Get NFL odds/spreads (replace YOUR_KEY)
# curl "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds?apiKey=660b36fc34c38f78fa89053211a6bf2a&regions=us&bookmakers=draftkings&markets=spreads&oddsFormat=american"

curl "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds" \
  -G --data-urlencode "apiKey=660b36fc34c38f78fa89053211a6bf2a" \
  --data-urlencode "regions=us" \
  --data-urlencode "bookmakers=draftkings" \
  --data-urlencode "markets=spreads" \
  --data-urlencode "oddsFormat=american" \
  --data-urlencode "commenceTimeFrom=2026-10-29T00:00:00Z" \
  --data-urlencode "commenceTimeTo=2026-11-03T06:00:00Z"
