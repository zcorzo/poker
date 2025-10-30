import time
import math
import random
from typing import List, Dict, Optional
from dataclasses import dataclass

from poker.deck import Deck
from poker.handeval import compare_hands
from ai.training import EvolutionTrainer


@dataclass
class Player:
    id: int
    stack: float
    genome_idx: int  # index into trainer.population
    highlight: bool = False  # mark survivors carried to next tournament


@dataclass
class Table:
    id: int
    players: List[Player]


class TournamentSimulator:
    def __init__(self, config: Dict, ui_event_queue, stop_event, trainer: EvolutionTrainer):
        self.cfg = config
        self.ui_event_queue = ui_event_queue
        self.stop_event = stop_event
        self.trainer = trainer
        self.rng = random.Random(config.get("random_seed", None))
        # State for highlighting and stats
        self.highlight_genome_idxs: set[int] = set()
        self.cumulative_hands: int = 0
        self.tournaments_run: int = 0
        self.baseline_spread: Optional[float] = None  # for convergence progress

    def initial_tables(self) -> List[Table]:
        tables = []
        pid = 1
        genomes_per_player = min(len(self.trainer.population), self.cfg["num_tables"] * self.cfg["players_per_table"])
        for t in range(self.cfg["num_tables"]):
            players = []
            for p in range(self.cfg["players_per_table"]):
                genome_idx = (pid - 1) % genomes_per_player
                players.append(Player(
                    id=pid,
                    stack=self.cfg["initial_bank"],
                    genome_idx=genome_idx,
                    highlight=(genome_idx in self.highlight_genome_idxs)
                ))
                pid += 1
            tables.append(Table(id=t + 1, players=players))
        return tables

    def emit_tables(self, tables: List[Table]):
        table_view = [[{"id": p.id, "stack": p.stack, "highlight": p.highlight} for p in tbl.players] for tbl in tables]
        self.ui_event_queue.put({"type": "update_tables", "tables": table_view})

    def level_parameters(self, level: int) -> Dict:
        sb = self.cfg["small_blind"] * (self.cfg["blind_increase_multiplier"] ** max(0, level - 1))
        bb = self.cfg["big_blind"] * (self.cfg["blind_increase_multiplier"] ** max(0, level - 1))
        ante = 0.0
        if self.cfg["ante_enabled"] and level >= int(self.cfg["ante_start_level"]):
            ante = self.cfg["ante_amount_bb_fraction"] * bb
        return {"sb": sb, "bb": bb, "ante": ante}

    def position_factor(self, idx: int, n: int) -> float:
        # Early/middle/late simple mapping for aggression scaling
        if idx < max(1, n // 3):
            return 0.3
        elif idx < max(2, 2 * n // 3):
            return 0.7
        return 1.0

    def play_hand(self, table: Table, level_params: Dict) -> Optional[int]:
        """
        Plays a simplified hand at a given table. Returns eliminated player id or None.
        Adds simple betting logic based on genome aggression and position to accelerate eliminations.
        """
        if len(table.players) <= 1:
            return None

        # Antes and blinds
        ante = level_params["ante"]
        sb = level_params["sb"]
        bb = level_params["bb"]

        # Rotate dealer button implicitly by rotating players list
        table.players = table.players[1:] + table.players[:1]

        # Collect antes
        pot = 0.0
        if ante > 0.0:
            for pl in table.players:
                paid = min(pl.stack, ante)
                pl.stack -= paid
                pot += paid

        # Blinds
        if len(table.players) >= 2:
            sb_player = table.players[0]
            bb_player = table.players[1]
            sb_paid = min(sb_player.stack, sb)
            bb_paid = min(bb_player.stack, bb)
            sb_player.stack -= sb_paid
            bb_player.stack -= bb_paid
            pot += sb_paid + bb_paid

        # Simple betting: each player commits extra chips based on aggression and position
        n = len(table.players)
        for idx, pl in enumerate(table.players):
            g = self.trainer.population[pl.genome_idx]
            pos_scale = self.position_factor(idx, n)
            # Ensure a minimum commitment to drive eliminations
            base_commit = bb * (0.5 + 0.8 * g.aggression) * pos_scale
            # Occasional bluff commit
            if self.rng.random() < min(0.6, g.bluff_freq + 0.3):
                base_commit += bb * 0.5
            # Short-stack shove behavior
            if pl.stack < 5 * bb and self.rng.random() < 0.5:
                commit = pl.stack
            else:
                commit = min(pl.stack, base_commit)
            pl.stack -= commit
            pot += commit

        # Deal cards
        deck = Deck(seed=self.rng.randint(0, 1_000_000))
        deck.shuffle()
        hole_cards = {}
        for pl in table.players:
            hole_cards[pl.id] = deck.deal(2)
        board = deck.deal(5)

        # Evaluate hands; find winner(s)
        best_pid = None
        ties = []
        for pl in table.players:
            if best_pid is None:
                best_pid = pl.id
                ties = [pl.id]
            else:
                c = compare_hands(hole_cards[pl.id], hole_cards[best_pid], board)
                if c > 0:
                    best_pid = pl.id
                    ties = [pl.id]
                elif c == 0:
                    if pl.id not in ties:
                        ties.append(pl.id)

        # Distribute pot to winner(s)
        if ties:
            share = pot / len(ties)
            for pl in table.players:
                if pl.id in ties:
                    pl.stack += share

        # Eliminate players with zero stack
        eliminated = None
        survivors = []
        for pl in table.players:
            if pl.stack <= 0.0:
                eliminated = pl.id
            else:
                survivors.append(pl)
        table.players = survivors
        return eliminated

    def reseat(self, tables: List[Table]) -> List[Table]:
        """
        Balance and break tables according to tournament rules:
        - Keep tables as even as possible.
        - Retire tables when overall player count no longer requires them.
        - Target max players per table from config.
        """
        # Flatten all players preserving relative order
        all_players: List[Player] = []
        for tbl in tables:
            all_players.extend(tbl.players)

        max_per_table = int(self.cfg["players_per_table"])
        total_players = len(all_players)
        # Compute target active tables: ceil(players / max_per_table), at least 1
        target_tables = max(1, math.ceil(total_players / max_per_table))

        new_tables: List[Table] = [Table(id=i + 1, players=[]) for i in range(target_tables)]

        # Distribute players round-robin to keep tables as even as possible
        ti = 0
        for pl in all_players:
            new_tables[ti % target_tables].players.append(pl)
            ti += 1

        # Ensure we don't exceed max_per_table by rebalancing if needed
        for tbl in new_tables:
            if len(tbl.players) > max_per_table:
                overflow = tbl.players[max_per_table:]
                tbl.players = tbl.players[:max_per_table]
                # place overflow onto next tables with space
                for pl in overflow:
                    for dest in new_tables:
                        if len(dest.players) < max_per_table:
                            dest.players.append(pl)
                            break

        return new_tables

    def run_single_tournament(self, progress_base: float, progress_scale: float) -> Dict:
        tables = self.initial_tables()
        self.emit_tables(tables)

        hands_played = 0
        level = 1
        level_params = self.level_parameters(level)

        # Track initial player count for progress within this tournament
        initial_players = sum(len(t.players) for t in tables)

        while True:
            if self.stop_event.is_set():
                break

            # Play a hand at each table
            eliminated_any = False
            for tbl in tables:
                elim = self.play_hand(tbl, level_params)
                if elim is not None:
                    self.ui_event_queue.put({"type": "elimination", "player_id": elim})
                    eliminated_any = True

            # Remove empty tables
            tables = [t for t in tables if len(t.players) > 0]
            # Reseat to balance if any elimination occurred
            if eliminated_any:
                tables = self.reseat(tables)
                self.emit_tables(tables)
                self.ui_event_queue.put({"type": "reseat", "tables": [[{"id": p.id, "stack": p.stack, "highlight": p.highlight} for p in tbl.players] for tbl in tables]})
            else:
                # No reseat, still emit updated stacks so UI reflects chip movements
                self.emit_tables(tables)

            hands_played += 1
            self.cumulative_hands += 1
            # Blind level increase
            if hands_played % int(self.cfg["blind_increase_hands"]) == 0:
                level += 1
                level_params = self.level_parameters(level)

            # Emit per-hand status (leave progress bar unchanged within tournament)
            total_players = sum(len(t.players) for t in tables)
            self.ui_event_queue.put({
                "type": "progress",
                "value": None,
                "text": f"Tournaments: {self.tournaments_run} | Cumulative hands: {self.cumulative_hands} | Hands this tournament: {hands_played} | Level: {level} | Players remaining: {total_players}"
            })

            # Sleep to simulate pace
            time.sleep(max(0.0, float(self.cfg["hand_speed_sec"])))

            # Check end of tournament
            if total_players <= 1:
                break

        # Collect survivors (final table players)
        survivors = []
        for tbl in tables:
            survivors.extend(tbl.players)
        return {
            "survivors": survivors,
            "hands_played": hands_played,
            "final_tables": tables,
        }

    def run_optimization(self):
        max_t = int(self.cfg["optimization_max_tournaments"])
        window = int(self.cfg["optimization_window"])
        eps = float(self.cfg["optimization_convergence_eps"])
        for t_idx in range(max_t):
            if self.stop_event.is_set():
                break

            # Compute base and scale for progress values within this tournament
            # Progress bar will represent convergence, updated after each tournament.
            self.ui_event_queue.put({"type": "progress", "value": None, "text": f"Tournament {t_idx + 1}/{max_t} started"})

            result = self.run_single_tournament(progress_base=0.0, progress_scale=0.0)
            self.tournaments_run += 1

            # Select top 10 survivors by stack to highlight next tournament
            survivors_sorted = sorted(result["survivors"], key=lambda p: p.stack, reverse=True)
            top_survivors = survivors_sorted[:10]
            self.highlight_genome_idxs = {p.genome_idx for p in top_survivors}

            # Advance evolution
            info = self.trainer.step()
            # Initialize baseline spread if not set
            if self.baseline_spread is None:
                self.baseline_spread = info["fitness_spread"]
            # Replace top survivors by elite
            survivor_genomes = [self.trainer.population[p.genome_idx] for p in top_survivors]
            self.trainer.evolve(survivor_genomes if survivor_genomes else info["elite"])

            # Convergence progress: based on fitness spread reduction
            current_spread = info["fitness_spread"]
            conv_progress = 0.0
            if self.baseline_spread and self.baseline_spread > 0:
                conv_progress = max(0.0, min(100.0, ((self.baseline_spread - current_spread) / self.baseline_spread) * 100.0))

            # Update progress at end of tournament
            self.ui_event_queue.put({"type": "progress", "value": conv_progress, "text": f"Completed {t_idx + 1}/{max_t} | Convergence {conv_progress:0.1f}%"})

            # Convergence check
            if self.trainer.check_convergence(window=window, eps=eps):
                best = self.trainer.best_ranges()
                self.ui_event_queue.put({"type": "progress", "value": 100.0, "text": "Converged"})
                return True, best

        best = self.trainer.best_ranges()
        return False, best