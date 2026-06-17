# CFBD Data We Can Use

The current CFBD API is enough to support several ranking styles.

## Best inputs for a power rating

- `games`: final scores, game state, home/away, venue, conference context
- `lines`: pregame market expectations for strength calibration
- `stats/season/advanced`: team efficiency and explosiveness style inputs
- `wepa/team/season`: opponent-adjusted efficiency signal
- `talent`: roster talent composite
- `rankings`: AP, Coaches, CFP, and other poll history for comparison only

## Recommended model layers

1. `Game strength`
   Use scores, location, and opponent quality to build Elo or another iterative rating.
2. `Efficiency strength`
   Blend advanced stats and WEPA to capture how good a team actually is under the hood.
3. `Market prior`
   Use closing lines early in the season so rankings are less noisy before sample size grows.
4. `Roster prior`
   Use talent as a preseason or early-season stabilizer, then reduce its weight over time.

## Suggested first build

If we want a practical version quickly, fetch:

- season games
- season lines
- team advanced stats
- team WEPA
- talent

Then create one feature table per team per week and blend:

- Elo
- win percentage
- strength of schedule
- scoring margin
- success-rate style efficiency
- explosiveness
- havoc allowed / created
- market residuals versus close

## Authentication

Set one of these environment variables before running the fetch script:

- `CFBD_API_KEY`
- `COLLEGEFOOTBALLDATA_API_KEY`

## Commands

```powershell
py fetch_cfbd_data.py games --year 2025
py fetch_cfbd_data.py ranking-inputs --year 2025
```
