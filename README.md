# College Football Power Rankings

This project builds a college football power rating from CollegeFootballData inputs.

The current model is a market-calibrated predictive power rating built for neutral-field matchups.

- `Neutral rating` is the estimated point value of a team relative to an average FBS team.
- `Neutral rating` is calibrated against CFBD market spreads, so team-to-team differences act like projected spreads.
- `Efficiency score` isolates how strong the team looks under the hood.
- `Market score` leans on CFBD Elo, spread performance, and talent.
- `Schedule score` captures how difficult the team profile has been to build.

## Project structure

- `power_rankings.py`: ranking engine and CLI entry point
- `cfbd_client.py`: lightweight CFBD API client
- `fetch_cfbd_data.py`: downloads CFBD inputs into local JSON files
- `build_team_features.py`: flattens CFBD season data into a reusable team feature table
- `inspect_cfbd_data.py`: summarizes raw CFBD payload coverage and schema
- `weekly_update.py`: runs the full weekly refresh pipeline end to end
- `refresh_public_app.py`: refreshes the public Streamlit outputs and optionally pushes them to GitHub
- `backtest_power_model.py`: evaluates weekly predictive performance on past seasons
- `dashboard_server.py`: serves a local UI for rankings, matchup lookup, and backtest review
- `app.py`: Streamlit app entrypoint for local use and shareable deployment
- `streamlit_app.py`: older Streamlit prototype kept for reference
- `project_win_totals.py`: projects future-season win totals from the current ratings and schedule
- `export_master_workbook.py`: combines current outputs into one spreadsheet workbook
- `tune_model.py`: runs a small historical parameter sweep to look for better backtest settings
- `data/sample_games.csv`: sample results you can replace with your own data
- `CFBD_NOTES.md`: recommended CFBD data sources for this project

## How to run

```powershell
py power_rankings.py
```

To compare two teams on a neutral field:

```powershell
py power_rankings.py --team-a "Ohio State" --team-b "Georgia"
```

To also export the full rankings:

```powershell
py power_rankings.py --save output/rankings.csv
```

To export an Excel workbook for sanity checking:

```powershell
py power_rankings.py --excel output/power_ratings_2025.xlsx
```

To fetch CFBD data after setting your API key:

```powershell
$env:CFBD_API_KEY="your-key-here"
py fetch_cfbd_data.py ranking-inputs --year 2025
```

To build a processed team feature table from the downloaded CFBD files:

```powershell
py build_team_features.py --year 2025
```

To prepare or run a full weekly update pipeline:

```powershell
py weekly_update.py --year 2025 --week 1 --dry-run
py weekly_update.py --year 2025 --week 1
```

To open the local dashboard:

```powershell
py dashboard_server.py
```

Then visit `http://127.0.0.1:8501`.

To run the Streamlit app locally:

```powershell
py -m streamlit run app.py
```

To deploy on Streamlit Community Cloud, push this repo to GitHub and choose `app.py` as the entrypoint file.

See `DEPLOYMENT.md` for the full deployment checklist. This project folder should be deployed as its own GitHub repo, not from the parent `C:\Users\joshn` git repo.

For hosted deployment, the app can work in either of these modes:

- commit the latest output CSV/XLSX files into the repo so the app loads them by default
- or upload the ratings/backtest files from the Streamlit sidebar after the app is live

To project future-season win totals from the current ratings:

```powershell
py project_win_totals.py --season 2026
```

The future schedule projection uses a fixed `2.5` points of home-field advantage when turning team ratings into projected spreads and win probabilities.

To export a single workbook with rankings, matchup tool, projections, and backtests:

```powershell
py export_master_workbook.py
```

To tune the prior-blend settings across multiple seasons:

```powershell
py tune_model.py --years 2023 2024 2025
```

To run a leakage-safe weekly backtest on a downloaded season:

```powershell
py backtest_power_model.py --year 2025 --season-type regular --save-games
```

## Ranking model

The rating script reads the processed team feature table and calibrates predictive signals against CFBD market lines:

- latest and average CFBD Elo strength
- CFBD Elo strength
- offensive and defensive efficiency
- opponent-adjusted WEPA
- recency-weighted form and cover performance
- performance versus the spread
- roster talent
- opponent quality

The `rating` column is expressed in points versus an average FBS team, so the difference between two teams is the projected neutral-field spread.

The model learns home-field advantage and feature coefficients directly from the downloaded line data.

## Backtesting

The historical backtest intentionally uses only leakage-safe features that would have been known at the time:

- team Elo context from completed prior games
- prior results and recency-weighted margins
- prior cover performance
- opponent quality from prior games
- talent

It does not use full-season advanced stats or WEPA in the weekly replay, because those season aggregates would leak future information unless we replace them with true week-by-week versions later.

## Weekly workflow

During the season, the simplest refresh path is:

1. Set `CFBD_API_KEY` and `ODDS_API_KEY` in the local environment
2. `py refresh_public_app.py --ratings-year 2025 --projection-year 2026 --push`
3. Check the Streamlit URL after GitHub finishes pushing

That command refreshes CFBD data, power ratings, projections, sportsbook odds, Excel exports, commits changed deployable outputs, and pushes to GitHub so Streamlit redeploys.

The repo also includes a GitHub Actions workflow that runs the same refresh every Monday at 14:00 UTC. Add `CFBD_API_KEY` and `ODDS_API_KEY` as repository secrets in GitHub so the scheduled job can pull fresh data without exposing either key.

For a local-only dry run without committing:

```powershell
py refresh_public_app.py --ratings-year 2025 --projection-year 2026 --skip-cfbd-fetch --skip-odds-fetch
```

## Next steps

- Replace the sample CSV with real game results
- Tune weights to match the kind of rankings you want
- Add conference filters, preseason priors, or playoff projections
