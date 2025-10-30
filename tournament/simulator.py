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
        self.highlight_genome_idxs: set[str] = set()
        self.cumulative_hands: int = 0
        self.tournaments_run: int = 0
        self.baseline_spread: Optional[float] = None  # for convergence progress
        # Economy: cumulative bankroll per genome (keyed by genome UID)
        self.genome_bankroll: Dict[str, float] = {}
        # Player registry for quick lookup (id -> Player)
        self.players_by_id: Dict[int, Player] = {}
        # Live payout locking when field reaches top-10
        self.top10_lock_active: bool = False
        self.locked_payouts: List[Dict] = []  # list of {"player_id":..., "uid":..., "payout":...}
        # Persistent player numbering: genome UID -> stable player_id, and global counter
        self.persistent_ids: Dict[str, int] = {}
        self.next_player_id: int = 1
        # Survivor counts: number of tournaments a genome has survived (advanced)
        self.survivor_counts: Dict[str, int] = {}

    def initial_tables(self) -> List[Table]:
        tables = []
        num_tables = int(self.cfg["num_tables"])
        seats_per_table = int(self.cfg["players_per_table"])
        pop = self.trainer.population
        uid_to_genome = {g.uid: g for g in pop}

        # Prepare highlighted genomes (top-10 finishers) and others
        highlighted_genomes = [uid_to_genome[uid] for uid in self.highlight_genome_idxs if uid in uid_to_genome]
        other_genomes = [g for g in pop if g.uid not in self.highlight_genome_idxs]

        # Distribute highlighted one per table (round-robin across tables)
        self.players_by_id = {}
        for t in range(num_tables):
            players = []
            # Seat one highlighted if available
            if highlighted_genomes:
                g = highlighted_genomes.pop(0)
                genome_idx = pop.index(g)
                # Assign persistent player id
                pid = self.persistent_ids.get(g.uid)
                if pid is None:
                    pid = self.next_player_id
                    self.persistent_ids[g.uid] = pid
                    self.next_player_id += 1
                pl = Player(
                    id=pid,
                    stack=self.cfg["initial_bank"],
                    genome_idx=genome_idx,
                    highlight=True
                )
                self.genome_bankroll.setdefault(g.uid, 0.0)
                players.append(pl)
                self.players_by_id[pid] = pl

            # Fill remaining seats from others
            while len(players) < seats_per_table:
                # Cycle through others; if exhausted, restart from beginning
                if not other_genomes:
                    other_genomes = pop[:]  # fallback to entire population
                g = other_genomes.pop(0)
                genome_idx = pop.index(g)
                # Assign persistent player id
                pid = self.persistent_ids.get(g.uid)
                if pid is None:
                    pid = self.next_player_id
                    self.persistent_ids[g.uid] = pid
                    self.next_player_id += 1
                pl = Player(
                    id=pid,
                    stack=self.cfg["initial_bank"],
                    genome_idx=genome_idx,
                    highlight=False
                )
                self.genome_bankroll.setdefault(g.uid, 0.0)
                players.append(pl)
                self.players_by_id[pid] = pl

            tables.append(Table(id=t + 1, players=players))

        return tables

    def emit_tables(self, tables: List[Table]):
        # Include cumulative bankroll in UI and emit best bankroll among current survivors.
        # Color survivors red if they have advanced in multiple tournaments.
        table_view = []
        current_bankrolls = []
        for tbl in tables:
            row = []
            for p in tbl.players:
                genome = self.trainer.population[p.genome_idx]
                b = self.genome_bankroll.get(genome.uid, 0.0)
                advanced_count = self.survivor_counts.get(genome.uid, 0)
                # highlight stays for top-10; red flag for multi-tournament survivors
                row.append({"id": p.id, "stack": p.stack, "highlight": p.highlight, "bankroll": b, "multi_survivor": advanced_count > 1})
                current_bankrolls.append(b)
            table_view.append(row)
        self.ui_event_queue.put({"type": "update_tables", "tables": table_view})
        if current_bankrolls:
            self.ui_event_queue.put({"type": "best_bankroll", "amount": max(current_bankrolls)})

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

        # Rebuild registry
        self.players_by_id = {}
        for tbl in new_tables:
            for pl in tbl.players:
                self.players_by_id[pl.id] = pl

        return new_tables

    def run_single_tournament(self, progress_base: float, progress_scale: float) -> Dict:
        tables = self.initial_tables()
        self.emit_tables(tables)

        hands_played = 0
        level = 1
        level_params = self.level_parameters(level)

        # Track initial player count for progress within this tournament
        initial_players = sum(len(t.players) for t in tables)

        # Economy: deduct buy-in from all entrants' cumulative bankroll
        buy_in = float(self.cfg.get("buy_in", 0.0))
        # Collect all entrants genomes from initial tables
        for tbl in tables:
            for pl in tbl.players:
                genome = self.trainer.population[pl.genome_idx]
                self.genome_bankroll[genome.uid] = self.genome_bankroll.get(genome.uid, 0.0) - buy_in

        # Track elimination order for payouts (players appended as they are eliminated)
        elimination_order: List[Player] = []

        while True:
            if self.stop_event.is_set():
                break

            # Play a hand at each table
            eliminated_any = False
            for tbl in tables:
                elim = self.play_hand(tbl, level_params)
                if elim is not None:
                    eliminated_any = True
                    # Lookup full player info from registry
                    pl = self.players_by_id.get(elim)
                    if pl:
                        elimination_order.append(pl)
                        # If in top-10 phase, lock payout for this elimination
                        if self.top10_lock_active:
                            idx_locked = len(self.locked_payouts)
                            payout_idx = 9 - idx_locked
                            distribution = self.cfg.get("payout_distribution", [])
                            prize_pool = buy_in * float(initial_players)
                            amt = prize_pool * float(distribution[payout_idx]) if 0 <= payout_idx < len(distribution) else 0.0
                            genome = self.trainer.population[pl.genome_idx]
                            self.genome_bankroll[genome.uid] = self.genome_bankroll.get(genome.uid, 0.0) + amt
                            self.locked_payouts.append({"player_id": pl.id, "uid": genome.uid, "payout": amt})
                        # Remove from registry
                        self.players_by_id.pop(elim, None)
                    self.ui_event_queue.put({"type": "elimination", "player_id": elim})

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

            # Activate payout locking when field reaches top-10
            total_players = sum(len(t.players) for t in tables)
            if not self.top10_lock_active and total_players <= 10:
                self.top10_lock_active = True

            # Emit per-hand status (leave progress bar unchanged within tournament)
            total_players = sum(len(t.players) for t in tables)
            self.ui_event_queue.put({
                "type": "progress",
                "value": None,
                "text": f"Tournaments: {self.tournaments_run} | Cumulative hands: {self.cumulative_hands} | Hands this tournament: {hands_played} | Level: {level} | Players remaining: {total_players}"
            })

            # Emit projected payouts live (based on current stacks) with top-10 locking
            prize_pool = buy_in * float(initial_players)
            distribution = self.cfg.get("payout_distribution", [])
            # Build current leaderboard by stack
            current_players = []
            for tbl in tables:
                for pl in tbl.players:
                    current_players.append(pl)
            current_players.sort(key=lambda p: p.stack, reverse=True)

            projections = []
            # First include locked payouts (players already eliminated during top-10 phase)
            for lp in self.locked_payouts:
                projections.append({"player_id": lp["player_id"], "payout": lp["payout"]})
            # Remaining payouts for still-in players: assign highest remaining payouts to current leaders
            remaining_slots = max(0, 10 - len(projections))
            remaining_payouts = []
            if distribution:
                # Remaining payout indexes from tail backwards based on already locked count
                for i in range(remaining_slots):
                    idx = 9 - len(self.locked_payouts) - i
                    if idx >= 0:
                        remaining_payouts.append(prize_pool * float(distribution[idx]))
            for i in range(min(remaining_slots, len(current_players))):
                projections.append({"player_id": current_players[i].id, "payout": remaining_payouts[i] if i < len(remaining_payouts) else 0.0})
            # Pad to always show 10 rows
            while len(projections) < 10:
                projections.append({"player_id": "-", "payout": 0.0})

            self.ui_event_queue.put({"type": "payout_projection", "projections": projections})

            # Sleep to simulate pace
            time.sleep(max(0.0, float(self.cfg["hand_speed_sec"])))

            # Check end of tournament
            if total_players <= 1:
                break

        # Collect survivors (final table players)
        survivors: List[Player] = []
        for tbl in tables:
            survivors.extend(tbl.players)

        # Economy: distribute prize pool among top finishers
        prize_pool = buy_in * float(initial_players)
        distribution = self.cfg.get("payout_distribution", [])

        # Build final finishing order: winner(s) first, then eliminated players reversed (last out gets higher place)
        finishing_order: List[Player] = []
        if survivors:
            survivors_sorted = sorted(survivors, key=lambda p: p.stack, reverse=True)
            finishing_order.extend(survivors_sorted)
        # Append eliminated players in reverse order
        for pl in reversed(elimination_order):
            finishing_order.append(pl)

        # Distribute payouts: if top-10 locking was active, pay remaining prizes to final placements
        if self.top10_lock_active:
            locked_count = len(self.locked_payouts)
            # Pay remaining prizes to final survivors (winner first)
            for i in range(min(10 - locked_count, len(survivors))):
                pl = survivors_sorted[i]
                idx = i  # winner gets index 0, etc.
                amt = prize_pool * float(distribution[idx]) if idx < len(distribution) else 0.0
                genome = self.trainer.population[pl.genome_idx]
                self.genome_bankroll[genome.uid] = self.genome_bankroll.get(genome.uid, 0.0) + amt
        else:
            # No locking (field never reached 10), pay top-10 by finishing order
            top_k = min(len(distribution), len(finishing_order))
            for i in range(top_k):
                pl = finishing_order[i]
                amt = prize_pool * float(distribution[i])
                # Map to genome uid
                genome = self.trainer.population[pl.genome_idx]
                self.genome_bankroll[genome.uid] = self.genome_bankroll.get(genome.uid, 0.0) + amt

        # Emit best bankroll for dashboard
        best_amt = max(self.genome_bankroll.values()) if self.genome_bankroll else 0.0
        self.ui_event_queue.put({"type": "best_bankroll", "amount": best_amt})

        # Prepare top-10 finisher UIDs for advancement (locked payouts first, then remaining survivors)
        top10_uids: List[str] = [lp["uid"] for lp in self.locked_payouts][:10]
        if len(top10_uids) < 10:
            for pl in survivors_sorted:
                uid = self.trainer.population[pl.genome_idx].uid
                if uid not in top10_uids:
                    top10_uids.append(uid)
                if len(top10_uids) >= 10:
                    break

        return {
            "survivors": survivors,
            "hands_played": hands_played,
            "final_tables": tables,
            "top10_uids": top10_uids,
        }

    def run_optimization(self):
        max_t = int(self.cfg["optimization_max_tournaments"])
        window = int(self.cfg["optimization_window"])
        eps = float(self.cfg["optimization_convergence_eps"])
        patience = int(self.cfg.get("optimization_patience_tournaments", 100))
        for t_idx in range(max_t):
            if self.stop_event.is_set():
                break

            # Reset payout lock and clear projection window for new tournament
            self.top10_lock_active = False
            self.locked_payouts = []
            self.ui_event_queue.put({"type": "payout_projection", "projections": []})

            # Start tournament
            self.ui_event_queue.put({"type": "progress", "value": None, "text": f"Tournament {t_idx + 1}/{max_t} started"})

            result = self.run_single_tournament(progress_base=0.0, progress_scale=0.0)
            self.tournaments_run += 1

            # Top-10 finisher UIDs from the tournament for advancement and highlight
            top10_uids = result.get("top10_uids", [])
            self.highlight_genome_idxs = set(top10_uids)
            # Update survivor counts
            for uid in top10_uids:
                self.survivor_counts[uid] = self.survivor_counts.get(uid, 0) + 1

            # Rank current population without evolving to compute convergence
            info = self.trainer.rank_population()
            # Initialize baseline spread if not set
            if self.baseline_spread is None:
                self.baseline_spread = info["fitness_spread"]

            # Replace population ensuring top-10 advance
            # Map UIDs to genomes in current population
            uid_to_genome = {g.uid: g for g in self.trainer.population}
            survivor_genomes = [uid_to_genome[uid] for uid in top10_uids if uid in uid_to_genome]
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

            # Patience early stop: stop if we've reached the configured patience count without convergence
            if (t_idx + 1) >= patience:
                best = self.trainer.best_ranges()
                return False, best

        best = self.trainer.best_ranges()
        return False, best