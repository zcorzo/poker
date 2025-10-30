import tkinter as tk
from tkinter import ttk


class ConfigView(ttk.Frame):
    def __init__(self, parent, config_state: dict, on_apply):
        super().__init__(parent)
        self.on_apply = on_apply
        self.inputs = {}
        self._build_form(config_state)

    def _add_entry(self, row, label, key, value):
        ttk.Label(self, text=label).grid(row=row, column=0, sticky=tk.W, padx=6, pady=2)
        var = tk.StringVar(value=str(value))
        entry = ttk.Entry(self, textvariable=var, width=12)
        entry.grid(row=row, column=1, sticky=tk.W, padx=6, pady=2)
        self.inputs[key] = var

    def _add_check(self, row, label, key, value):
        ttk.Label(self, text=label).grid(row=row, column=0, sticky=tk.W, padx=6, pady=2)
        var = tk.BooleanVar(value=bool(value))
        chk = ttk.Checkbutton(self, variable=var)
        chk.grid(row=row, column=1, sticky=tk.W, padx=6, pady=2)
        self.inputs[key] = var

    def _build_form(self, cfg):
        row = 0
        ttk.Label(self, text="Tournament Configuration", font=("TkDefaultFont", 12, "bold")).grid(row=row, column=0, columnspan=2, pady=(6, 6))
        row += 1

        self._add_entry(row, "Tables", "num_tables", cfg["num_tables"]); row += 1
        self._add_entry(row, "Players per table", "players_per_table", cfg["players_per_table"]); row += 1
        self._add_entry(row, "Initial bank ($)", "initial_bank", cfg["initial_bank"]); row += 1
        self._add_entry(row, "Small blind ($)", "small_blind", cfg["small_blind"]); row += 1
        self._add_entry(row, "Big blind ($)", "big_blind", cfg["big_blind"]); row += 1
        self._add_check(row, "Enable ante", "ante_enabled", cfg["ante_enabled"]); row += 1
        self._add_entry(row, "Ante start level", "ante_start_level", cfg["ante_start_level"]); row += 1
        self._add_entry(row, "Ante amount (BB fraction)", "ante_amount_bb_fraction", cfg["ante_amount_bb_fraction"]); row += 1
        self._add_entry(row, "Blind increase every N hands", "blind_increase_hands", cfg["blind_increase_hands"]); row += 1
        self._add_entry(row, "Blind increase multiplier", "blind_increase_multiplier", cfg["blind_increase_multiplier"]); row += 1
        self._add_entry(row, "Hand speed (sec/hand)", "hand_speed_sec", cfg["hand_speed_sec"]); row += 1
        self._add_entry(row, "Max tournaments", "optimization_max_tournaments", cfg["optimization_max_tournaments"]); row += 1
        self._add_entry(row, "Convergence epsilon", "optimization_convergence_eps", cfg["optimization_convergence_eps"]); row += 1
        self._add_entry(row, "Convergence window", "optimization_window", cfg["optimization_window"]); row += 1
        self._add_check(row, "Reset optimization", "reset_optimization", cfg.get("reset_optimization", False)); row += 1
        self._add_entry(row, "Random seed", "random_seed", cfg["random_seed"]); row += 1

        btn = ttk.Button(self, text="Apply", command=self._apply_click)
        btn.grid(row=row, column=0, columnspan=2, pady=(8, 4))

        for i in range(2):
            self.columnconfigure(i, weight=1)

    def _apply_click(self):
        def parse(v):
            try:
                if v.isdigit():
                    return int(v)
                return float(v)
            except Exception:
                return v

        new_cfg = {}
        for k, var in self.inputs.items():
            val = var.get()
            if isinstance(var, tk.BooleanVar):
                new_cfg[k] = bool(val)
            else:
                new_cfg[k] = parse(str(val))
        self.on_apply(new_cfg)


class TournamentView(ttk.Frame):
    def __init__(self, parent, start_cb, stop_cb):
        super().__init__(parent)
        self.start_cb = start_cb
        self.stop_cb = stop_cb
        self.table_frames = []
        self.player_labels = {}  # player_id -> label ref

        # Controls
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=6, pady=2)
        ttk.Button(ctrl, text="Start Simulation", command=self.start_cb).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl, text="Stop Simulation", command=self.stop_cb).pack(side=tk.LEFT, padx=2)

        # Canvas for tables
        self.canvas = ttk.Frame(self)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def build_tables(self, num_tables, players_per_table):
        # Clear old frames
        for f in self.table_frames:
            f.destroy()
        self.table_frames = []
        self.player_labels = {}

        # Build grid of tables
        cols = min(4, max(1, int(num_tables ** 0.5)))
        rows = (num_tables + cols - 1) // cols

        idx = 0
        for r in range(rows):
            row_frame = ttk.Frame(self.canvas)
            row_frame.pack(fill=tk.X, expand=False, pady=2)
            for c in range(cols):
                if idx >= num_tables:
                    break
                tf = ttk.LabelFrame(row_frame, text=f"Table {idx + 1}")
                tf.pack(side=tk.LEFT, padx=4, pady=2, fill=tk.BOTH, expand=True)
                self.table_frames.append(tf)

                # placeholders
                for p in range(players_per_table):
                    player_id = idx * players_per_table + p + 1
                    lbl = ttk.Label(tf, text=str(player_id), relief=tk.GROOVE, width=4)
                    lbl.grid(row=p // 5, column=p % 5, padx=2, pady=2)
                    self.player_labels[player_id] = lbl
                idx += 1

    def update_tables(self, tables):
        # tables: list of lists of player_ids
        # Clear current and rebuild labels per table
        for tf in self.table_frames:
            for child in tf.winfo_children():
                child.destroy()

        self.player_labels = {}
        for ti, tf in enumerate(self.table_frames):
            players = tables[ti] if ti < len(tables) else []
            tf.config(text=f"Table {ti + 1} ({len(players)} players)")
            for idx, pid in enumerate(players):
                lbl = ttk.Label(tf, text=str(pid), relief=tk.GROOVE, width=4)
                lbl.grid(row=idx // 5, column=idx % 5, padx=2, pady=2)
                self.player_labels[pid] = lbl

    def eliminate_player(self, player_id):
        lbl = self.player_labels.get(player_id)
        if lbl:
            lbl.config(text="", relief=tk.FLAT)


class ResultsView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.text = tk.Text(self, wrap=tk.NONE, height=30)
        self.text.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def display_ranges(self, ranges):
        # ranges: dict with keys: preflop, postflop; each contains position-based matrices
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, "Optimized Betting Ranges\n\n")

        def fmt_matrix(name, mat):
            s = f"{name}:\n"
            for row in mat:
                s += " ".join(f"{v:0.2f}" for v in row) + "\n"
            s += "\n"
            return s

        pre = ranges.get("preflop", {})
        post = ranges.get("postflop", {})
        for pos in ["early", "middle", "late"]:
            if pos in pre:
                self.text.insert(tk.END, fmt_matrix(f"Preflop ({pos})", pre[pos]))
        for pos in ["early", "middle", "late"]:
            if pos in post:
                self.text.insert(tk.END, fmt_matrix(f"Postflop ({pos})", post[pos]))