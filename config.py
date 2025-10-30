DEFAULT_CONFIG = {
    "num_tables": 11,
    "players_per_table": 9,
    "initial_bank": 1000,
    "small_blind": 5,
    "big_blind": 10,
    "ante_enabled": True,
    "ante_start_level": 3,            # introduce ante at level 3 (less aggressive)
    "ante_amount_bb_fraction": 0.2,   # ante = 0.2 BB (less aggressive than 0.25)
    "blind_increase_hands": 50,       # increase blinds every 50 hands (less aggressive)
    "blind_increase_multiplier": 1.5, # 1.5x per level (typical tournament progression)
    "hand_speed_sec": 1.0,            # target pace: one hand per second

    # Optimization settings
    "optimization_max_tournaments": 50,
    "optimization_convergence_eps": 0.02,  # threshold for convergence of ranges
    "optimization_window": 5,         # rolling window to check stability
    "reset_optimization": False,
    "random_seed": 42,

    # Economy settings
    "buy_in": 100,  # cost per tournament per player (deducted from cumulative bankroll)
    # Default payout distribution for top 10 finishers (should sum to 1.0)
    "payout_distribution": [0.25, 0.18, 0.14, 0.11, 0.09, 0.08, 0.06, 0.04, 0.03, 0.02],
}

# Notes:
# - Blinds/antes: modeled per-hand level increases; configurable to match typical tournament structures.
# - Economy: Each player pays buy_in at tournament start (cumulative bankroll decreases). Prize pool equals total buy-ins.
#   Top 10 receive payouts according to payout_distribution. You can customize these via the Configuration tab.