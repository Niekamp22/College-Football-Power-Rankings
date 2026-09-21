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
- `review_completed_games.py`: grades completed games against the model, market lines, and final scores
- `export_master_workbook.py`: combines current outputs into one spreadsheet workbook
- `tune_model.py`: runs a small historical parameter sweep to look for better backtest settings
- `margin_challenger.py`: validates matchup and market-residual features on a held-out season before production use
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
Unrated FCS opponents are assigned a conservative low baseline rating so early-season FBS/FCS mismatch projections do not treat them like lower-tier FBS teams.
FCS-involved games use a wider `20.0` point margin standard deviation for win probabilities because their observed scoring variance is materially higher than FBS-only games.

The odds and results-review outputs classify FCS edges separately. An FCS favorite edge from `5.0` to under `15.0` points is a qualified lean. FCS underdog edges, edges below `5.0`, and edges of `15.0+` are marked as passes. The raw model spread remains visible for auditing; this policy changes confidence and bet classification, not the underlying team rating.

To export a single workbook with rankings, matchup tool, projections, and backtests:

```powershell
py export_master_workbook.py
```

To review completed games against the model and market:

```powershell
py review_completed_games.py --season 2026
```

## Dual rating system

The production `rating` is a validated blend of two separately built components:

- `football_rating` uses completed FBS game margins capped at 35 points and an Elo/talent prior.
- `market_rating` solves team strength directly from available FBS point spreads.
- `rating` blends 60% football rating with 40% market rating. This blend performed best on the combined market-and-actual objective in walk-forward tests across 2023-2025.

`market_gap` is market rating minus football rating. Large absolute gaps and limited FBS samples reduce `rating_confidence` so disagreements remain visible instead of being hidden inside the final number.

In leakage-safe weekly replays across the 2023-2025 regular seasons, the dual system improved actual-margin MAE from `13.200` to `12.466`, improved market-distance MAE from `4.956` to `3.149`, and increased outright winner accuracy from `68.9%` to `72.7%`. ATS edge-side accuracy remained near 50%, so betting recommendations still require the separate edge filters and review flags.

Every refresh also runs `snapshot_rankings.py`. The first ratings generated for an upcoming week are saved under `output/snapshots/<season>` and are not overwritten. Completed-game review uses a matching weekly snapshot when available and labels older games without a snapshot as `current_retrospective`.

## Odds history and CLV

Every Odds API refresh appends a normalized snapshot to `output/odds/odds_history.csv`. The app compares every sportsbook, selects the best available spread and price for the model side, calculates the price-adjusted break-even probability, and reports the improvement over the consensus line.

`output/odds/clv_summary.csv` tracks opening-to-latest movement and calculates closing-line value after kickoff. Positive CLV means the captured number was better than the final pregame consensus. The ATS classifier is guarded by `validate_ats_signal.py`; it is not deployed unless its held-out Brier score beats the baseline model.

The podcast shortlist is intentionally stricter than the general odds board. Candidates must be FBS-only, have a moderate model edge, be offered by at least four books at `-120` or better, involve medium-or-better rating confidence, avoid spreads above 14 points and large internal rating gaps, and receive support from both rating components. These safeguards improve candidate quality but do not represent a validated ATS probability.

Every refresh also runs `margin_challenger.py`. New matchup features remain research-only unless they improve held-out margin MAE and clear the ATS-side validation gate; failed experiments are retained in the Validation view instead of silently changing production.

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
2. `py refresh_public_app.py --ratings-year 2026 --projection-year 2026 --push`
3. Check the Streamlit URL after GitHub finishes pushing

That command refreshes CFBD data, power ratings, projections, sportsbook odds, Excel exports, commits changed deployable outputs, and pushes to GitHub so Streamlit redeploys.

The repo also includes a GitHub Actions workflow that runs the same refresh every Monday at 14:00 UTC. Add `CFBD_API_KEY` and `ODDS_API_KEY` as repository secrets in GitHub so the scheduled job can pull fresh data without exposing either key.

For a local-only dry run without committing:

```powershell
py refresh_public_app.py --ratings-year 2026 --projection-year 2026 --skip-cfbd-fetch --skip-odds-fetch
```

## Next steps

- Replace the sample CSV with real game results
- Tune weights to match the kind of rankings you want
- Add conference filters, preseason priors, or playoff projections
