#!/usr/bin/env python
"""Train the build -> win model and run it against the wealth-baseline gate.

The gate is the point of this script. An item model's AUC is meaningless in
isolation because item ownership encodes wealth, and wealth predicts winning.
What matters is the lift over a model that sees only wealth and context.

Usage:  python scripts/train_model_a.py [purchases.parquet]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

from deadlock import assets, confound, design

LGB_PARAMS = dict(
    objective="binary",
    learning_rate=0.05,
    num_leaves=63,
    min_child_samples=100,
    feature_fraction=0.7,
    bagging_fraction=0.8,
    bagging_freq=1,
    verbose=-1,
)
N_ROUNDS = 400


def _fit(x_train, y_train, x_test, y_test):
    train_set = lgb.Dataset(x_train, label=y_train)
    valid_set = lgb.Dataset(x_test, label=y_test, reference=train_set)
    model = lgb.train(
        LGB_PARAMS,
        train_set,
        num_boost_round=N_ROUNDS,
        valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    probs = model.predict(x_test, num_iteration=model.best_iteration)
    return model, float(roc_auc_score(y_test, probs)), float(log_loss(y_test, probs))


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/processed/purchases.parquet")
    df = pd.read_parquet(path)
    logging.info("loaded %s: %d purchases, %d matches", path, len(df), df.match_id.nunique())

    item_ids = sorted(assets.upgrade_ids())
    hero_ids = sorted(assets.playable_heroes())

    # The early-game window is the honest framing. Wealth relative to enemies
    # correlates 0.16 with winning in phase 0 but 0.60 by phase 3, so a
    # full-match model is largely scored on the outcome restating itself. The
    # early window is also when a recommendation is actually actionable.
    for window_name, max_phase in (
        ("early game (phases 0-1)", 1),
        ("full match (phases 0-3)", 3),
    ):
        window = design.restrict_phases(df, max_phase)
        print()
        print("#" * 68)
        print(f"# WINDOW: {window_name} -- {len(window):,} purchases")
        print("#" * 68)

        for split_name, splitter in (
            ("random-by-match", confound.split_by_match),
            ("time-ordered", confound.split_by_time),
        ):
            print()
            print("=" * 68)
            print(f"SPLIT: {split_name}")
            print("=" * 68)
            train_df, test_df = splitter(window)

            baseline = confound.wealth_baseline(train_df, test_df)
            print(f"\n{baseline}   [linear, purchase rows]")

            x_ctl_tr, y_tr, _, _ = design.build_design(
                train_df, item_ids, hero_ids, include_items=False
            )
            x_ctl_te, y_te, _, _ = design.build_design(
                test_df, item_ids, hero_ids, include_items=False
            )
            _, ctl_auc, ctl_ll = _fit(x_ctl_tr, y_tr, x_ctl_te, y_te)
            print(f"controls-only GBM   AUC={ctl_auc:.4f}  logloss={ctl_ll:.4f}")

            x_tr, y_tr, names, _ = design.build_design(train_df, item_ids, hero_ids)
            x_te, y_te, _, _ = design.build_design(test_df, item_ids, hero_ids)
            model, item_auc, item_ll = _fit(x_tr, y_tr, x_te, y_te)
            print(f"full item model     AUC={item_auc:.4f}  logloss={item_ll:.4f}")

            ctl_result = confound.BaselineResult(
                ctl_auc, x_ctl_tr.shape[0], x_ctl_te.shape[0], pd.Series(dtype=float)
            )
            print()
            print(confound.report_gate(item_auc, ctl_result))

            if split_name == "random-by-match" and max_phase == 1:
                _report_importance(model, names, item_ids)
                _report_stratified(window)

    return 0


def _report_importance(model, names: list[str], item_ids: list[int]) -> None:
    """Gain importance, grouped per item across its phase columns."""
    gains = model.feature_importance(importance_type="gain")
    series = pd.Series(gains, index=names)

    items = assets.load_items()
    per_item: dict[str, float] = {}
    for item_id in item_ids:
        cols = [f"item_{item_id}_p{p}" for p in range(4)]
        total = float(series.reindex(cols).fillna(0).sum())
        if total > 0:
            name = items[item_id].name if item_id in items else str(item_id)
            per_item[name] = total

    print("\ntop 15 items by gain (summed across phases):")
    top = pd.Series(per_item).sort_values(ascending=False).head(15)
    print(top.round(1).to_string())

    print("\ntop 10 non-item features by gain:")
    non_item = series[~series.index.str.startswith("item_")]
    print(non_item.sort_values(ascending=False).head(10).round(1).to_string())


def _report_stratified(df: pd.DataFrame) -> None:
    """Model-free cross-check: wealth-adjusted item win rates."""
    rates = confound.stratified_item_winrate(df, min_matches=200)
    if rates.empty:
        print("\n(no items met the min_matches threshold)")
        return
    items = assets.load_items()
    rates = rates.copy()
    rates["item"] = [items[i].name if i in items else str(i) for i in rates.index]

    cols = ["item", "raw_win_rate", "adjusted_win_rate", "wealth_inflation", "n"]
    print("\ntop 10 items by wealth-adjusted win rate:")
    print(rates[cols].head(10).round(4).to_string(index=False))
    print("\nmost wealth-inflated (raw flattered by rich buyers):")
    print(rates.nlargest(10, "wealth_inflation")[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    raise SystemExit(main())
