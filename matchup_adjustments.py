from __future__ import annotations


FBS_MARGIN_STD_DEV = 16.0
FCS_MARGIN_STD_DEV = 20.0
FCS_QUALIFIED_EDGE_MIN = 5.0
EXTREME_EDGE_MIN = 15.0


def matchup_margin_std_dev(home_classification: str | None, away_classification: str | None) -> float:
    classifications = {
        str(home_classification or "").lower(),
        str(away_classification or "").lower(),
    }
    return FCS_MARGIN_STD_DEV if "fcs" in classifications else FBS_MARGIN_STD_DEV


def betting_status(
    game_type_label: str,
    edge_home_points: float | None,
    market_home_spread: float | None,
    schedule_match_status: str = "exact",
) -> str:
    if schedule_match_status == "unmatched":
        return "Pass - schedule unmatched"
    if edge_home_points is None or market_home_spread is None:
        return "No current market line"

    absolute_edge = abs(edge_home_points)
    if game_type_label != "FCS involved":
        return "Review - extreme edge" if absolute_edge >= EXTREME_EDGE_MIN else "Standard"

    if absolute_edge >= EXTREME_EDGE_MIN:
        return "Pass - FCS extreme edge"

    picked_market_spread = market_home_spread if edge_home_points > 0 else -market_home_spread
    if picked_market_spread > 0:
        return "Pass - FCS underdog"
    if picked_market_spread == 0:
        return "Pass - FCS pick'em"
    if absolute_edge < FCS_QUALIFIED_EDGE_MIN:
        return "Pass - FCS low edge"
    return "Qualified FCS favorite"
