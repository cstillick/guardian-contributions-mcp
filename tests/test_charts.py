"""Chart renderers + chart-data + per-period unitemized split."""
from conftest import seed_roe_store

from guardian_contrib import service
from guardian_contrib.web import charts


def test_renderers_produce_svg_or_empty():
    assert '<svg class="chart"' in charts.line_chart([("2026-06-04", 100000), ("2026-06-11", 350000)])
    assert '<svg class="chart"' in charts.hbar_chart([("A", 5000), ("B", 3000)])
    assert '<svg class="chart"' in charts.segmented_bar([("Individuals", 1000), ("PACs", 3000)])
    assert "chart-empty" in charts.line_chart([])          # empty state, no crash
    assert "chart-empty" in charts.segmented_bar([])


def test_periods_and_unitemized_identity(temp_db):
    seed_roe_store()
    p = service.get_periods("11932")
    assert p["periods"], "Pre-Primary period should be present"
    row = p["periods"][0]
    # unitemized is always reported-raised minus itemized cash, clamped at 0
    assert row["unitemized_cents"] == max(0, row["raised_cents"] - row["itemized_cents"])
    assert p["totals"]["raised_cents"] >= p["totals"]["itemized_cents"] - 1


def test_chart_data_functions(temp_db):
    seed_roe_store()
    assert service.series_for_orgs(["11932"])              # cumulative series, non-empty
    assert service.funding_sources("11932")                # source breakdown
    top = service.top_contributors("11932")
    assert top and top[0][1] >= top[-1][1]                 # sorted descending by amount
