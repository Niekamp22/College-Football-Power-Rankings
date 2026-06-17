const state = {
  ratings: [],
  conferences: [],
  teams: [],
  backtest: [],
};

const sourceBadge = document.getElementById("sourceBadge");
const teamASelect = document.getElementById("teamASelect");
const teamBSelect = document.getElementById("teamBSelect");
const conferenceFilter = document.getElementById("conferenceFilter");
const teamSearch = document.getElementById("teamSearch");
const ratingsBody = document.querySelector("#ratingsTable tbody");
const backtestBody = document.querySelector("#backtestTable tbody");
const matchupOutput = document.getElementById("matchupOutput");
const backtestStats = document.getElementById("backtestStats");

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${url}`);
  }
  return response.json();
}

function formatPct(value) {
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function populateSelect(select, values) {
  select.innerHTML = values.map((value) => `<option value="${value}">${value}</option>`).join("");
}

function renderConferenceFilter() {
  const options = [`<option value="all">All conferences</option>`].concat(
    state.conferences.map((conference) => `<option value="${conference}">${conference}</option>`)
  );
  conferenceFilter.innerHTML = options.join("");
}

function renderRatingsTable() {
  const selectedConference = conferenceFilter.value || "all";
  const searchTerm = teamSearch.value.trim().toLowerCase();
  const rows = state.ratings.filter((row) => {
    const conferenceMatch = selectedConference === "all" || row.conference === selectedConference;
    const searchMatch = !searchTerm || String(row.team).toLowerCase().includes(searchTerm);
    return conferenceMatch && searchMatch;
  });

  ratingsBody.innerHTML = rows
    .map(
      (row, index) => `
        <tr>
          <td>${index + 1}</td>
          <td>${row.team}</td>
          <td>${row.conference}</td>
          <td>${row.record}</td>
          <td>${Number(row.rating).toFixed(2)}</td>
          <td>${Number(row.efficiency_score).toFixed(2)}</td>
          <td>${Number(row.market_score).toFixed(2)}</td>
          <td>${Number(row.schedule_score).toFixed(2)}</td>
        </tr>
      `
    )
    .join("");
}

function renderBacktestTable() {
  backtestBody.innerHTML = state.backtest
    .map(
      (row) => `
        <tr>
          <td>${row.week}</td>
          <td>${row.games}</td>
          <td>${Number(row.model_vs_market_mae).toFixed(3)}</td>
          <td>${Number(row.model_vs_actual_mae).toFixed(3)}</td>
          <td>${Number(row.actual_vs_market_mae).toFixed(3)}</td>
          <td>${Number(row.model_vs_market_corr).toFixed(3)}</td>
        </tr>
      `
    )
    .join("");
}

function renderBacktestStats() {
  if (!state.backtest.length) {
    backtestStats.innerHTML = `<div class="metric-card"><span class="metric-label">Backtest</span><strong class="metric-value">Unavailable</strong></div>`;
    return;
  }
  const latest = state.backtest[state.backtest.length - 1];
  const overallGames = state.backtest.reduce((sum, row) => sum + Number(row.games), 0);
  const weightedMae =
    state.backtest.reduce((sum, row) => sum + Number(row.model_vs_market_mae) * Number(row.games), 0) / overallGames;
  const weightedCorr =
    state.backtest.reduce((sum, row) => sum + Number(row.model_vs_market_corr) * Number(row.games), 0) / overallGames;

  const cards = [
    ["Tracked Games", overallGames.toString()],
    ["Weighted MAE", weightedMae.toFixed(3)],
    ["Weighted Corr", weightedCorr.toFixed(3)],
    ["Latest Week", String(latest.week)],
  ];

  backtestStats.innerHTML = cards
    .map(
      ([label, value]) => `
        <div class="metric-card">
          <span class="metric-label">${label}</span>
          <strong class="metric-value">${value}</strong>
        </div>
      `
    )
    .join("");
}

async function renderMatchup() {
  const teamA = teamASelect.value;
  const teamB = teamBSelect.value;
  if (!teamA || !teamB) {
    return;
  }

  const matchup = await fetchJson(`/api/matchup?team_a=${encodeURIComponent(teamA)}&team_b=${encodeURIComponent(teamB)}`);
  if (matchup.error) {
    matchupOutput.innerHTML = `<div class="metric-card"><span class="metric-label">Error</span><strong class="metric-value">${matchup.error}</strong></div>`;
    return;
  }

  const spreadLabel =
    matchup.spread >= 0
      ? `${matchup.team_a} -${matchup.favorite_spread.toFixed(1)}`
      : `${matchup.team_b} -${matchup.favorite_spread.toFixed(1)}`;

  matchupOutput.innerHTML = `
    <div class="metric-card">
      <span class="metric-label">Projected Spread</span>
      <strong class="metric-value">${spreadLabel}</strong>
    </div>
    <div class="metric-card">
      <span class="metric-label">${matchup.team_a} Win %</span>
      <strong class="metric-value">${formatPct(matchup.team_a_win_probability)}</strong>
    </div>
    <div class="metric-card">
      <span class="metric-label">${matchup.team_b} Win %</span>
      <strong class="metric-value">${formatPct(matchup.team_b_win_probability)}</strong>
    </div>
  `;
}

async function init() {
  const [ratingsPayload, backtestPayload] = await Promise.all([
    fetchJson("/api/ratings"),
    fetchJson("/api/backtest"),
  ]);

  state.ratings = ratingsPayload.ratings || [];
  state.conferences = ratingsPayload.conferences || [];
  state.teams = ratingsPayload.teams || [];
  state.backtest = backtestPayload.weekly || [];

  sourceBadge.textContent = `Ratings: ${ratingsPayload.source}`;
  populateSelect(teamASelect, state.teams);
  populateSelect(teamBSelect, state.teams);
  if (state.teams.length > 1) {
    teamBSelect.selectedIndex = 1;
  }
  renderConferenceFilter();
  renderRatingsTable();
  renderBacktestTable();
  renderBacktestStats();
  await renderMatchup();
}

conferenceFilter.addEventListener("change", renderRatingsTable);
teamSearch.addEventListener("input", renderRatingsTable);
teamASelect.addEventListener("change", renderMatchup);
teamBSelect.addEventListener("change", renderMatchup);

init().catch((error) => {
  sourceBadge.textContent = "Failed to load dashboard data";
  console.error(error);
});
