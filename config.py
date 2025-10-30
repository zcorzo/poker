DEFAULT_CONFIG = {
    "num_tables": 11,
    "players_per_table": 9,
    "initial_bank": 1000,
    "small_blind": 5,
    "big_blind": 10,
    "ante_enabled": True,
    "ante_start_level": 1,          # start ante at level 1 to speed up eliminations
    "ante_amount_bb_fraction": 0.25,  # ante as fraction of big blind
    "blind_increase_hands": 10,     # increase blinds more frequently for faster tournaments
    "blind_increase_multiplier": 2.0,
    "hand_speed_sec": 1.0,          # target pace: one hand per second
    "optimization_max_tournaments": 50,
    "optimization_convergence_eps": 0.02,  # threshold for convergence of ranges
    "optimization_window": 5,       # rolling window to check stability
    "reset_optimization": False,
    "random_seed": 42,
}

# Notes on blinds and antes:
# There is no single "official" universal schedule. Major events (e.g., WSOP) use time-based levels
# (commonly 20-60 minutes per level) with increasing blinds and antes each level.
# We model it as hand-count-based levels for simulation convenience, but this is configurable.