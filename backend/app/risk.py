"""Scoring and avoidance helpers for predicted barrier risk (cells come from forecast.predict).

Risk is the predicted chance of an accessibility 311 report in a cell over the next 3 days
(base rate about 6%). It is advisory: routing may prefer lower-risk streets but never
treats risk as a confirmed obstruction.
"""

from shapely.geometry import LineString, Point, box, shape

HIGH_RISK = 0.3      # ~6x the base rate; about 40% of such cell-days get a report
ELEVATED_RISK = 0.1  # below this, a detour isn't worth the extra distance
MIN_LENGTH = 1e-6    # degrees (~0.1 m); ignores paths that only touch a cell edge


def _shapes(cells: list[dict]):
    return [(cell, shape(cell["geometry"])) for cell in cells]


def query_cells(cells: list[dict], bounds=None) -> list[dict]:
    if not bounds:
        return cells
    area = box(*bounds)
    return [cell for cell, geometry in _shapes(cells) if geometry.intersects(area)]


def avoid_candidates(cells: list[dict], bounds, endpoints) -> list[dict]:
    """Elevated-risk cells in bounds, except those holding an endpoint (ORS could never route)."""
    area = box(*bounds)
    points = [Point(point) for point in endpoints]
    return [cell for cell, geometry in _shapes(cells)
            if cell["properties"]["risk"] >= ELEVATED_RISK and geometry.intersects(area)
            and not any(geometry.intersects(point) for point in points)]


def cutoffs(cells: list[dict]) -> list[float]:
    """Thresholds to try, from avoiding the riskiest half of candidate cells to the riskiest tenth."""
    risks = sorted(cell["properties"]["risk"] for cell in cells)
    if not risks:
        return []
    return sorted({risks[min(len(risks) - 1, int(len(risks) * quantile))] for quantile in (.5, .75, .9)})


def score_path(cells: list[dict], coordinates) -> dict:
    """Length-weighted mean and max risk of the cells a path crosses."""
    path = LineString(coordinates)
    crossed = []
    for cell, geometry in _shapes(cells):
        if geometry.intersects(path):
            length = geometry.intersection(path).length
            if length >= MIN_LENGTH:
                crossed.append((cell["properties"]["risk"], length))
    total = sum(length for _, length in crossed)
    return {
        "max": max((risk for risk, _ in crossed), default=0),
        "mean": round(sum(risk * length for risk, length in crossed) / total, 3) if total else 0,
        "cells_crossed": len(crossed),
        "high_risk_cells": sum(risk >= HIGH_RISK for risk, _ in crossed),
        "high_risk_share": round(sum(length for risk, length in crossed if risk >= HIGH_RISK) / total, 3) if total else 0,
    }
