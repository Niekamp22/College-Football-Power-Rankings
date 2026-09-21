# Streamlit Deployment

This app is designed to deploy on Streamlit Community Cloud with `app.py` as the entrypoint.

## Files the hosted app needs

The app reads prebuilt CSV/XLSX outputs by default:

- `output/cfbd_power_ratings_current.csv`
- `output/backtests/weekly_backtest_2025_regular.csv`
- `output/projections/projected_win_totals_2026.csv`
- `output/projections/projected_games_2026.csv`
- `output/odds/ncaaf_game_odds_comparison.csv`
- `output/power_ratings_final.xlsx`

If any of those files are missing on Streamlit Cloud, the sidebar upload controls can be used as a fallback.

## Local test

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## GitHub setup

This project folder should be its own GitHub repository. Do not deploy from the parent `C:\Users\joshn` git repo.

```powershell
git init
git add .
git commit -m "Prepare Streamlit deployment"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## Streamlit Cloud setup

1. Go to Streamlit Community Cloud.
2. Choose the GitHub repo for this project.
3. Set the main file path to `app.py`.
4. Add secrets in the Streamlit app settings if you later run API refreshes from the hosted app.

Current hosted mode does not require secrets because it reads committed output files.

## Data refresh

The production refresh runs automatically from `.github/workflows/weekly-refresh.yml` every Monday at 14:17 UTC. During daylight time that is 10:17 AM Eastern; during standard time it is 9:17 AM Eastern. The off-hour start reduces GitHub scheduler congestion.

### One-time GitHub setup

In the GitHub repository, open **Settings > Secrets and variables > Actions** and add these repository secrets:

- `CFBD_API_KEY`
- `ODDS_API_KEY`

Real keys must never be committed to the repository. The scheduled workflow verifies both secrets before making any API calls.

### What the automation does

1. Runs the complete unit test suite.
2. Downloads current CFBD inputs and sportsbook odds.
3. Rebuilds ratings, frozen weekly snapshots, projections, reviews, analytics, and Excel outputs.
4. Runs `validate_public_outputs.py` as a publication gate.
5. Treats incomplete schedules as warnings, not failures.
6. Commits and pushes only validated outputs, causing Streamlit to redeploy automatically.
7. Uploads a refresh log and `output/refresh_status.json` as a GitHub Actions artifact.

If any command or validation check fails, the workflow exits before committing, leaving the previous good public data online.

### Manual refresh

Open the repository's **Actions** tab, choose **Weekly data refresh**, and select **Run workflow**. This uses the same guarded pipeline as the Monday schedule.

For a local refresh:

```powershell
$env:CFBD_API_KEY="your-key"
$env:ODDS_API_KEY="your-key"
py refresh_public_app.py --ratings-year 2026 --projection-year 2026 --push
```
