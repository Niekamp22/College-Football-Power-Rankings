# Streamlit Deployment

This app is designed to deploy on Streamlit Community Cloud with `app.py` as the entrypoint.

## Files the hosted app needs

The app reads prebuilt CSV/XLSX outputs by default:

- `output/cfbd_power_ratings_2025.csv`
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

Refresh data locally, then commit the updated outputs:

```powershell
py power_rankings.py --save output/cfbd_power_ratings_2025.csv --excel output/power_ratings_final.xlsx
py project_win_totals.py --season 2026
py sync_odds_api.py
py export_master_workbook.py
git add output app.py requirements.txt .streamlit/config.toml
git commit -m "Refresh model outputs"
git push
```
