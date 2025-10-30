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

    def initial_tables(self) -> List[Table]:
        tables = []
        pid = 1
        genomes_per_player = min(len(self.trainer.population), self.cfg["num_tables"] * self.cfg["players_per_table"])
        for t in range(self.cfg["num_tables"]):
            players = []
            for p in range(self.cfg["players_per_table"]):
                genome_idx = (pid - 1) % genomes_per_player
                players.append(Player(id=pid, stack=self.cfg["initial_bank"], genome_idx=genome_idx))
                pid += 1
            tables.append(Table(id=t + 1, players=players))
        return tables

    def emit_tables(self, tables: List[Table]):
        table_view = [[p.id for p in tbl.players] for tbl in tables]
        self.ui_event_queue.put({"type": "update_tables", "tables": table_view})

    def level_parameters(self, level: int) -> Dict:
        sb = self.cfg["small_blind"] * (self.cfg["blind_increase_multiplier"] ** max(0, level - 1))
        bb = self.cfg["big_blind"] * (self.cfg["blind_increase_multiplier"] ** max(0, level - 1))
        ante = 0.0
        if self.cfg["ante_enabled"] and level >= int(self.cfg["ante_start_level"]):
            ante = self.cfg["ante_amount_bb_fraction"] * bb
        return {"sb": sb, "bb": bb, "ante": ante}

    def play_hand(self, table: Table, level_params: Dict) -> Optional[int]:
        """
        Plays a simplified hand at a given table. Returns eliminated player id or None.
        For now, betting logic is simplified; we deal cards, pick a winner by hand evaluation.
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
        if ante > 0.0:
            for pl in table.players:
                paid = min(pl.stack, ante)
                pl.stack -= paid

        # Blinds
        if len(table.players) >= 2:
            sb_player = table.players[0]
            bb_player = table.players[1]
            sb_player.stack -= min(sb_player.stack, sb)
            bb_player.stack -= min(bb_player.stack, bb)

        # Deal cards
        deck = Deck(seed=self.rng.randint(0, 1_000_000))
        deck.shuffle()
        hole_cards = {}
        for pl in table.players:
            hole_cards[pl.id] = deck.deal(2)
        board = deck.deal(5)

        # Evaluate hands; split pot to winner(s)
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

        # Pot size approximated as sum of blinds + antes
        pot = sb + bb + ante * len(table.players)
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
        # Flatten players and redistribute to keep tables balanced
        all_players = []
        for tbl in tables:
            all_players.extend(tbl.players)
        # Compute target distribution
        num_tables = len([t for t in tables if t is not None])
        per_table = max(1, len(all_players) // num_tables)
        new_tables = []
        idx = 0
        for t in range(num_tables):
            plist = []
            for _ in range(per_table):
                if idx < len(all_players):
                    plist.append(all_players[idx])
                    idx += 1
            new_tables.append(Table(id=t + 1, players=plist))
        # Distribute remaining players one per table
        ti = 0
        while idx < len(all_players):
            new_tables[ti % num_tables].players.append(all_players[idx])
            idx += 1
            ti += 1
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
                self.ui_event_queue.put({"type": "reseat", "tables": [[p.id for p in tbl.players] for tbl in tables]})

            hands_played += 1
            # Blind level increase
            if hands_played % int(self.cfg["blind_increase_hands"]) == 0:
                level += 1
                level_params = self.level_parameters(level)

            # Emit per-hand status to show activity, with numeric progress value
            total_players = sum(len(t.players) for t in tables)
            # Tournament progress: fraction of players eliminated
            elim_frac = 0.0
            if initial_players > 1:
                elim_frac = (initial_players - total_players) / (initial_players - 1)
            overall_pct = progress_base + progress_scale * (elim_frac * 100.0)
            self.ui_event_queue.put({
                "type": "progress",
                "value": overall_pct,
                "text": f"Hands: {hands_played} | Level: {level} | Players remaining: {total_players}"
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
            base_pct = (t_idx / max_t) * 100.0
            scale_pct = (1.0 / max_t) * 100.0

            # Emit tournament start progress
            self.ui_event_queue.put({"type": "progress", "value": base_pct, "text": f"Tournament {t_idx + 1}/{max_t} started"})

            result = self.run_single_tournament(progress_base=base_pct, progress_scale=scale_pct)
            # Map survivors to genomes
            survivor_genomes = [self.trainer.population[p.genome_idx] for p in result["survivors"]]
            # Advance evolution
            info = self.trainer.step()
            # Replace top survivors by elite
            self.trainer.evolve(survivor_genomes if survivor_genomes else info["elite"])

            # Update progress at end of tournament
            end_pct = ((t_idx + 1) / max_t) * 100.0
            self.ui_event_queue.put({"type": "progress", "value": end_pct, "text": f"Completed {t_idx + 1}/{max_t}"})

            # Convergence check
            if self.trainer.check_convergence(window=window, eps=eps):
                best = self.trainer.best_ranges()
                self.ui_event_queue.put({"type": "progress", "value": 100.0, "text": "Converged"})
                return True, best

        best = self.trainer.best_ranges()
        return False, best