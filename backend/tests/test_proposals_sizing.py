from app.services import proposals, risk


def _cfg(**overrides):
    base = {
        "max_position_pct": 0.10,
        "max_total_exposure_pct": 0.80,
        "core_symbol": "RSP",
        "core_target_pct": 0.70,
        "core_rebalance_threshold_pct": 0.02,
    }
    base.update(overrides)
    return base


def test_cap_buy_qty_respects_existing_position_cap():
    account = {"equity": 100_000.0, "buying_power": 100_000.0}
    positions = [{"symbol": "MS", "qty": 30.0, "market_value": 6_500.0}]

    qty = proposals._cap_buy_qty_for_risk(
        account, positions, "MS", qty=30, price=217.58, cfg=_cfg()
    )

    assert qty == 16
    decision = risk.validate_order(account, positions, "MS", "buy", qty, 217.58)
    assert decision.ok
    too_many = risk.validate_order(account, positions, "MS", "buy", qty + 1, 217.58)
    assert not too_many.ok
    assert "position would" in too_many.reason


def test_cap_core_buy_qty_respects_total_exposure_overlay_budget():
    account = {"equity": 100_000.0, "buying_power": 100_000.0}
    positions = [
        {"symbol": "CSCO", "qty": 42.0, "market_value": 5_400.0},
        {"symbol": "AMD", "qty": 6.0, "market_value": 3_100.0},
        {"symbol": "C", "qty": 49.0, "market_value": 6_600.0},
        {"symbol": "MS", "qty": 30.0, "market_value": 6_500.0},
        {"symbol": "GS", "qty": 5.0, "market_value": 5_500.0},
        {"symbol": "LLY", "qty": 4.0, "market_value": 4_500.0},
        {"symbol": "MU", "qty": 4.0, "market_value": 4_000.0},
        {"symbol": "CDNS", "qty": 10.0, "market_value": 4_100.0},
        {"symbol": "MAR", "qty": 16.0, "market_value": 6_300.0},
        {"symbol": "OTHER", "qty": 1.0, "market_value": 7_000.0},
    ]  # total invested = 53,000, leaving only 27,000 before the 80% cap.

    cfg = _cfg()
    qty = proposals._cap_buy_qty_for_risk(
        account, positions, "RSP", qty=330, price=209.565, cfg=cfg
    )

    assert qty == 128
    decision = risk.validate_order(account, positions, "RSP", "buy", qty, 209.565, cfg=cfg)
    assert decision.ok
    too_many = risk.validate_order(
        account, positions, "RSP", "buy", qty + 1, 209.565, cfg=cfg
    )
    assert not too_many.ok
    assert "total exposure" in too_many.reason


def test_virtual_buy_prevents_second_same_cycle_proposal_from_exceeding_cap():
    account = {"equity": 100_000.0, "buying_power": 100_000.0}
    positions = []
    cfg = _cfg(core_target_pct=0.0)

    first_qty = proposals._cap_buy_qty_for_risk(account, positions, "AAPL", 80, 100.0, cfg)
    proposals._apply_virtual_buy(positions, "AAPL", first_qty, 100.0)
    second_qty = proposals._cap_buy_qty_for_risk(account, positions, "AAPL", 80, 100.0, cfg)

    assert first_qty == 80
    assert second_qty == 20
    assert risk.validate_order(account, positions, "AAPL", "buy", second_qty, 100.0).ok
    assert not risk.validate_order(account, positions, "AAPL", "buy", second_qty + 1, 100.0).ok


def test_core_rebalance_sells_weak_non_core_holdings_to_make_rsp_room():
    equity = 100_000.0
    cfg = _cfg()
    positions = [
        {"symbol": "RSP", "qty": 150.0, "market_value": 32_000.0, "current_price": 213.33},
        {"symbol": "WEAK", "qty": 100.0, "market_value": 30_000.0, "current_price": 300.0},
        {"symbol": "MID", "qty": 100.0, "market_value": 25_000.0, "current_price": 250.0},
        {"symbol": "STRONG", "qty": 100.0, "market_value": 18_000.0, "current_price": 180.0},
    ]
    reco = {
        "WEAK": {"symbol": "WEAK", "score": -0.3, "rank_score": -1.0, "reasons": ["weakest"]},
        "MID": {"symbol": "MID", "score": 0.1, "rank_score": 0.2, "reasons": ["middle"]},
        "STRONG": {"symbol": "STRONG", "score": 0.8, "rank_score": 2.0, "reasons": ["strongest"]},
    }

    sells = proposals._core_rebalance_sell_candidates(cfg, positions, equity, reco)

    assert [s[0] for s in sells] == ["WEAK", "MID", "STRONG"]
    assert sum(qty * price for _sym, qty, price, _d in sells) >= 63_000.0
    assert "core rebalance" in sells[0][3]["reasons"][0]


def test_core_rebalance_sells_nothing_when_rsp_can_be_bought_from_cash():
    equity = 100_000.0
    cfg = _cfg()
    positions = [
        {"symbol": "RSP", "qty": 150.0, "market_value": 32_000.0, "current_price": 213.33},
        {"symbol": "AAPL", "qty": 10.0, "market_value": 5_000.0, "current_price": 500.0},
    ]

    sells = proposals._core_rebalance_sell_candidates(cfg, positions, equity, {})

    assert sells == []


def test_core_buy_becomes_possible_after_rebalance_sells_are_applied():
    equity = 100_000.0
    account = {"equity": equity, "buying_power": 100_000.0}
    cfg = _cfg()
    positions = [
        {"symbol": "RSP", "qty": 150.0, "market_value": 32_000.0, "current_price": 213.33},
        {"symbol": "WEAK", "qty": 100.0, "market_value": 30_000.0, "current_price": 300.0},
        {"symbol": "MID", "qty": 100.0, "market_value": 25_000.0, "current_price": 250.0},
        {"symbol": "STRONG", "qty": 100.0, "market_value": 18_000.0, "current_price": 180.0},
    ]
    reco = {"RSP": {"symbol": "RSP", "price": 200.0}}

    assert proposals._cap_buy_qty_for_risk(account, positions, "RSP", 190, 200.0, cfg) == 0
    for sym, _qty, _price, _d in proposals._core_rebalance_sell_candidates(
        cfg, positions, equity, {}
    ):
        proposals._apply_virtual_sell(positions, sym)

    core = proposals._core_buy_candidate(cfg, account, positions, equity, reco, regime="risk_on")
    assert core is not None
    sym, qty, price, _d = core
    capped_qty = proposals._cap_buy_qty_for_risk(account, positions, sym, qty, price, cfg)

    assert sym == "RSP"
    assert capped_qty > 0
    assert risk.validate_order(account, positions, sym, "buy", capped_qty, price, cfg=cfg).ok
