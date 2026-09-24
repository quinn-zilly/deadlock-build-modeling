"""A refit must not leave the CLI serving models fitted on the old tables.

The CLI caches its fitted models beside the tables and reuses them for as long
as the file exists. `refit.py` used to rebuild every table under those caches
and leave them in place, so after a refit the CLI still answered from models
two weeks older than the tables.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refit.py"


def load_script():
    spec = importlib.util.spec_from_file_location("refit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["refit"] = module
    spec.loader.exec_module(module)
    return module


refit = load_script()

MODELS = [
    "sequence_model.npz",
    "sequence_model.index.json",
    "sequence_model_all.npz",
    "sequence_model_all.index.json",
    "sequence_model_b55.npz",
    "ability_model.npz",
    "ability_model.index.json",
    "ability_model_all.npz",
]
TABLES = ["purchases.parquet", "abilities.parquet", "archetypes.parquet"]


def processed(tmp_path: Path) -> Path:
    for name in [*MODELS, *TABLES, "counter_lifts.parquet"]:
        (tmp_path / name).write_text("x")
    return tmp_path


class TestClearCaches:
    def test_every_cached_model_goes_in_every_bracket(self, tmp_path):
        refit.clear_caches(processed(tmp_path), "archetypes")
        assert not any((tmp_path / name).exists() for name in MODELS)

    def test_the_tables_stay(self, tmp_path):
        refit.clear_caches(processed(tmp_path), "purchases")
        assert all((tmp_path / name).exists() for name in TABLES)

    def test_counters_go_when_the_purchase_table_is_rebuilt(self, tmp_path):
        refit.clear_caches(processed(tmp_path), "purchases")
        assert not (tmp_path / "counter_lifts.parquet").exists()

    def test_counters_stay_when_the_purchase_table_does(self, tmp_path):
        # They read only the purchase table, which a later start keeps.
        refit.clear_caches(processed(tmp_path), "archetypes")
        assert (tmp_path / "counter_lifts.parquet").exists()

    def test_a_rebuild_of_the_builds_alone_keeps_the_models(self, tmp_path):
        # Neither the tables nor the labels change after the archetype step.
        refit.clear_caches(processed(tmp_path), "builds")
        assert all((tmp_path / name).exists() for name in MODELS)

    def test_reports_what_it_removed(self, tmp_path):
        removed = refit.clear_caches(processed(tmp_path), "archetypes")
        assert sorted(p.name for p in removed) == sorted(MODELS)

    def test_nothing_cached_is_not_an_error(self, tmp_path):
        assert refit.clear_caches(tmp_path, "purchases") == []
