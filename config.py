DEFAULT_CONFIG = {
    "num_tables": 11,
    "players_per_table": 9,
    "initial_bank": 1000,
    "small_blind": 5,
    "big_blind": 10,
    "ante_enabled": True,
    "ante_start_level": 3,            # introduce ante at level 3 (less aggressive)
    "ante_amount_bb_fraction": 0.2,   # ante = 0.2 BB
    "blind_increase_hands": 70,       # slower blind progression to reduce variance
    "blind_increase_multiplier": 1.35,# gentler increase across levels
    "hand_speed_sec": 0.1,            # target pace: 0.1 sec per hand
    "ui_min_update_interval_sec": 0.05,  # throttle UI updates to at most 20 FPS

    # Optimization settings
    "optimization_max_tournaments": 50,
    "optimization_convergence_eps": 0.01,  # tighter convergence threshold
    "optimization_window": 5,         # rolling window to check stability
    "optimization_min_tournaments_for_convergence": 10,  # require at least N tournaments before converging
    "optimization_patience_tournaments": 100,  # stop early if no convergence after this many tournaments
    "reset_optimization": False,
    "random_seed": 42,

    # Economy settings
    "buy_in": 1000,  # cost per tournament per player (deducted from cumulative bankroll)
    # Default payout distribution for top 10 finishers (should sum to 1.0)
    "payout_distribution": [0.25, 0.18, 0.14, 0.11, 0.09, 0.08, 0.06, 0.04, 0.03, 0.02],
}

# Notes:
# - Blinds/antes: modeled per-hand level increases; configurable to match typical tournament structures.
# - Economy: Each player pays buy_in at tournament start (cumulative bankroll decreases). Prize pool equals total buy-ins.
#   Top 10 receive payouts according to payout_distribution. You can customize these via the Configuration tab.
# - Optimization: The optimizer uses tournament performance scores to evolve ranges and will only declare convergence
#   after a minimum number of tournaments and a tighter stability threshold. It will stop early if patience is exceeded.