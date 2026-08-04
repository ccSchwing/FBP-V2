You do not need the json file any longer.
To create a schedule for the week:
1. Select the week's games from 2025-schedule
2. Place that into a new Numbers sheet
3. Export the sheet.
4. Rename the exported sheet to weekN-schedule.csv
5. run ~/bin/sync-to-s3.sh to copy the file to the my-fbp.com bucket.
6. The ImportSpreadsAndFinalScores lambda will read the csv file and update the Schedule table with the spreads.

This same Lambda can be used to up the Final Scores as well.
