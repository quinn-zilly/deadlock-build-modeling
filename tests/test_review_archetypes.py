"""The review sheet is the hard stop a person reads before Stage 4.

A share printed without its weight is the failure these tests exist for: the
sheet once put a share over 24 rows next to one over 5,110 and made them read
as the same claim.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_archetypes.py"


def load_script():
    spec = importlib.util.spec_from_file_location("review_archetypes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["review_archetypes"] = module
    spec.loader.exec_module(module)
    return module


review = load_script()


def cluster(n: int, name: str = "Spirit Ivy") -> dict:
    return {
        "name": name,
        "share": 0.5,
        "n": n,
        "naming_margin": 2.0,
        "family_name": name,
        "centroid": {"share_spirit": 1.0},
        "top_items": [
            {"item_id": 1, "name": "Mystic Burst", "in_cluster": 0.96, "elsewhere": 0.1}
        ],
    }


def meta_for(*clusters: dict) -> dict:
    return {
        "seed": 0,
        "heroes": {
            "1": {
                "hero_name": "Ivy",
                "k": len(clusters),
                "n": sum(c["n"] for c in clusters),
                "reason": "",
                "criteria": {
                    "separation": {"value": 0.5, "threshold": 0.45, "passed": True}
                },
                "archetypes": list(clusters),
            }
        },
    }


class TestThinShares:
    def test_a_share_from_too_few_players_is_marked(self):
        """24 rows is not a finding, and the sheet has to say so."""
        import pandas as pd

        text = review.sheet(meta_for(cluster(24), cluster(5000)), pd.DataFrame())
        assert "[thin: 24 players]" in text

    def test_a_well_populated_share_is_not_marked(self):
        """The mark has to mean something, so it cannot be on everything."""
        import pandas as pd

        text = review.sheet(meta_for(cluster(5000), cluster(4000)), pd.DataFrame())
        assert "thin" not in text

    def test_the_item_shares_of_a_thin_cluster_are_marked_too(self):
        """96% of 24 players is the number that misled, not the cluster size."""
        import pandas as pd

        text = review.sheet(meta_for(cluster(24), cluster(5000)), pd.DataFrame())
        row = [ln for ln in text.splitlines() if "Mystic Burst" in ln][0]
        assert "[thin: 24 players]" in row

    @pytest.mark.parametrize("n", [29, 30])
    def test_the_threshold_is_thirty(self, n):
        """Stated once, in the module, so the sheet and the namer agree."""
        assert bool(review.thin_note(n)) is (n < review.MIN_ROWS)
        assert review.MIN_ROWS == 30
