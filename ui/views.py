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

        # Economy settings
        self._add_entry(row, "Buy-in ($)", "buy_in", cfg.get("buy_in", 1000)); row += 1
        # For payout distribution, accept comma-separated percentages/fractions; we store as comma string
        payout_str = ",".join(str(x) for x in cfg.get("payout_distribution", []))
        self._add_entry(row, "Payout distribution (comma fractions)", "payout_distribution", payout_str); row += 1

        # Optimization settings
        self._add_entry(row, "Max tournaments", "optimization_max_tournaments", cfg["optimization_max_tournaments"]); row += 1
        self._add_entry(row, "Convergence epsilon", "optimization_convergence_eps", cfg["optimization_convergence_eps"]); row += 1
        self._add_entry(row, "Convergence window", "optimization_window", cfg["optimization_window"]); row += 1
        self._add_entry(row, "Patience (tournaments)", "optimization_patience_tournaments", cfg.get("optimization_patience_tournaments", 100)); row += 1
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
                sval = str(val)
                if k == "payout_distribution":
                    try:
                        # parse comma-separated floats
                        parts = [p.strip() for p in sval.split(",") if p.strip()]
                        new_cfg[k] = [float(p) for p in parts]
                    except Exception:
                        new_cfg[k] = []
                else:
                    new_cfg[k] = parse(sval)
        self.on_apply(new_cfg)


class TournamentView(ttk.Frame):
    def __init__(self, parent, start_cb, stop_cb):
        super().__init__(parent)
        # Remove frame padding to eliminate gray space
        self.configure(padding=0)
        self.start_cb = start_cb
        self.stop_cb = stop_cb
        self.table_frames = []
        self.player_labels = {}  # player_id -> label ref

        # Styles with zero padding
        style = ttk.Style()
        style.configure("NoPad.TFrame", padding=0)
        style.configure("NoPad.TLabelframe", padding=0)
        style.configure("NoPad.TLabelframe.Label", padding=0)

        # Controls (use pack consistently to avoid geometry manager conflicts)
        ctrl = ttk.Frame(self, style="NoPad.TFrame")
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
        # Left controls
        left_ctrl = ttk.Frame(ctrl, style="NoPad.TFrame")
        left_ctrl.pack(side=tk.LEFT, padx=0, pady=0)
        ttk.Button(left_ctrl, text="Start Simulation", command=self.start_cb).pack(side=tk.LEFT, padx=2, pady=0)
        ttk.Button(left_ctrl, text="Stop Simulation", command=self.stop_cb).pack(side=tk.LEFT, padx=2, pady=0)

        # Body: split into left tables and right sidebar
        body = ttk.Frame(self, style="NoPad.TFrame")
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Right sidebar: best bankroll and payout projections
        right_info = ttk.Frame(body, style="NoPad.TFrame")
        right_info.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=0)
        self.best_bankroll_var = tk.StringVar(value="Best bankroll: $0")
        ttk.Label(right_info, textvariable=self.best_bankroll_var).pack(side=tk.TOP, anchor="e")

        # Live payout projections
        self.payout_tree = ttk.Treeview(right_info, columns=("place", "player", "stack", "payout"), show="headings", height=18)
        self.payout_tree.heading("place", text="Place")
        self.payout_tree.heading("player", text="Player")
        self.payout_tree.heading("stack", text="Stack")
        self.payout_tree.heading("payout", text="Projected Payout")
        self.payout_tree.column("place", width=50, anchor="e")
        self.payout_tree.column("player", width=80, anchor="e")
        self.payout_tree.column("stack", width=80, anchor="e")
        self.payout_tree.column("payout", width=120, anchor="e")
        self.payout_tree.pack(side=tk.TOP, anchor="e", fill=tk.Y, expand=False)

        # Dedicated tables container to keep layout stable and avoid jumping
        self.tables_container = ttk.Frame(body, style="NoPad.TFrame")
        self.tables_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0, pady=0)
        # Use a Canvas with a fixed height to anchor content at the top and add a vertical scrollbar
        self.tables_canvas = tk.Canvas(self.tables_container, height=420, borderwidth=0, highlightthickness=0)
        self.tables_canvas.pack(side=tk.LEFT, anchor="n", fill=tk.BOTH, expand=True)
        self.tables_scroll = ttk.Scrollbar(self.tables_container, orient="vertical", command=self.tables_canvas.yview)
        self.tables_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tables_canvas.configure(yscrollcommand=self.tables_scroll.set)
        # Inner frame inside the canvas where tables are built
        self.canvas_inner = ttk.Frame(self.tables_canvas, style="NoPad.TFrame")
        self.tables_canvas.create_window((0, 0), window=self.canvas_inner, anchor="nw")
        # Keep scrollregion in sync
        self.canvas_inner.bind("<Configure>", lambda e: self.tables_canvas.configure(scrollregion=self.tables_canvas.bbox("all")))
        # Mouse wheel scrolling (Windows)
        self.tables_canvas.bind_all("<MouseWheel>", lambda e: self.tables_canvas.yview_scroll(-1*(e.delta//120), "units"))

    def clear_payouts(self):
        # Clear all rows in the payout projection tree
        if hasattr(self, "payout_tree") and self.payout_tree is not None:
            for i in self.payout_tree.get_children():
                self.payout_tree.delete(i)

    def build_tables(self, num_tables, players_per_table):
        # Clear old frames
        for f in getattr(self, "table_frames", []):
            f.destroy()
        self.table_frames = []
        self.player_labels = {}

        # Build grid of tables inside the stable inner canvas frame
        parent = getattr(self, "canvas_inner", self)
        # Clear any children previously added directly (safety)
        for child in parent.winfo_children():
            child.destroy()

        cols = min(4, max(1, int(num_tables ** 0.5)))
        rows = (num_tables + cols - 1) // cols

        idx = 0
        for r in range(rows):
            row_frame = ttk.Frame(parent, style="NoPad.TFrame")
            row_frame.pack(side=tk.TOP, anchor="n", fill=tk.X, expand=False, pady=0)
            for c in range(cols):
                if idx >= num_tables:
                    break
                tf = ttk.LabelFrame(row_frame, text=f"Table {idx + 1}", style="NoPad.TLabelframe")
                tf.pack(side=tk.LEFT, padx=2, pady=0, fill=tk.BOTH, expand=True)
                self.table_frames.append(tf)

                # placeholders (ID and stack placeholder)
                for p in range(players_per_table):
                    player_id = idx * players_per_table + p + 1
                    lbl = ttk.Label(tf, text=f"{player_id}\n$", relief=tk.GROOVE, width=8, anchor="center", justify="center")
                    lbl.grid(row=(p // 5), column=p % 5, padx=1, pady=1)
                    self.player_labels[player_id] = lbl
                idx += 1

    def update_tables(self, tables):
        # tables: list of lists of dicts: {"id":..., "stack":..., "highlight": bool, "bankroll": float}
        # Clear and rebuild labels per table
        for tf in self.table_frames:
            for child in tf.winfo_children():
                child.destroy()

        self.player_labels = {}
        for ti, tf in enumerate(self.table_frames):
            players = tables[ti] if ti < len(tables) else []
            tf.config(text=f"Table {ti + 1} ({len(players)} players)")
            for idx, pinfo in enumerate(players):
                if isinstance(pinfo, dict):
                    pid = pinfo.get("id")
                    stack = pinfo.get("stack", 0)
                    bankroll = pinfo.get("bankroll", 0)
                    highlight = bool(pinfo.get("highlight", False))
                    multi_survivor = bool(pinfo.get("multi_survivor", False))
                    text = f"{pid}\n${int(stack)}\nB:${int(bankroll)}"
                else:
                    pid = pinfo
                    highlight = False
                    multi_survivor = False
                    text = str(pid)
                # Background: green for current highlighted top-10, red if survived multiple tournaments
                bg = "#c7f9cc" if highlight else ( "#ffcccc" if multi_survivor else None )
                lbl = tk.Label(tf, text=text, bg=bg, relief=tk.GROOVE, width=10, anchor="center", justify="center")
                lbl.grid(row=(idx // 5), column=idx % 5, padx=2, pady=2)
                self.player_labels[pid] = lbl

    def set_best_bankroll(self, player_id: int, amount: float):
        if player_id is None:
            self.best_bankroll_var.set(f"Best bankroll: ${int(amount)}")
        else:
            self.best_bankroll_var.set(f"Best bankroll: #{player_id} ${int(amount)}")

    def update_payouts(self, projections):
        # projections: list in rank order: [{"player_id":..., "payout":..., "stack":...}, ...] length 10
        # refresh treeview
        for i in self.payout_tree.get_children():
            self.payout_tree.delete(i)
        for rank, item in enumerate(projections, start=1):
            stack_val = item.get("stack", 0)
            self.payout_tree.insert("", "end", values=(rank, item["player_id"], int(stack_val), f"${int(item['payout'])}"))

    def eliminate_player(self, player_id):
        lbl = self.player_labels.get(player_id)
        if lbl:
            lbl.config(text="", relief=tk.FLAT)


class ResultsView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        # Save latest ranges for export
        self._latest_ranges = None

        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=6, pady=4)
        save_btn = ttk.Button(toolbar, text="Save Ranges", command=self._save_ranges)
        save_btn.pack(side=tk.LEFT)

        # Scrollable container
        self.canvas = tk.Canvas(self, borderwidth=0)
        self.scroll_y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll_y.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _save_ranges(self):
        if not self._latest_ranges:
            return
        try:
            import json
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(title="Save Ranges", defaultextension=".json", filetypes=[("JSON", "*.json")])
            if path:
                with open(path, "w") as f:
                    json.dump(self._latest_ranges, f, indent=2)
        except Exception:
            pass

    def display_ranges(self, ranges):
        self._latest_ranges = ranges
        # Clear previous content
        for child in self.scroll_frame.winfo_children():
            child.destroy()

        ttk.Label(self.scroll_frame, text="Optimized Betting Ranges", font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(2, 6))

        # Color mapping thresholds
        def action_color(v: float) -> str:
            if v is None:
                return "#808080"
            if v < 0.33:
                return "#808080"  # fold
            elif v < 0.66:
                return "#f0ad4e"  # call
            else:
                return "#d9534f"  # raise

        ranks = "23456789TJQKA"

        def combo_label(i: int, j: int) -> str:
            if i == j:
                return ranks[i] + ranks[j]
            # upper triangle suited, lower offsuit
            hi = max(i, j)
            lo = min(i, j)
            if i < j:
                return ranks[hi] + ranks[lo] + "s"
            else:
                return ranks[hi] + ranks[lo] + "o"

        def render_matrix(parent, title: str, mat):
            frame = ttk.LabelFrame(parent, text=title)
            frame.pack(fill=tk.X, padx=2, pady=4)

            # Grid of colored squares with labels
            for i in range(len(mat)):
                for j in range(len(mat[i])):
                    v = mat[i][j]
                    color = action_color(v)
                    lbl = tk.Label(frame, text=combo_label(i, j), bg=color, fg="black", width=4)
                    lbl.grid(row=i, column=j, padx=1, pady=1, sticky="nsew")

            # Make cells expand uniformly
            rows = len(mat)
            cols = len(mat[0]) if mat else 0
            for i in range(rows):
                frame.rowconfigure(i, weight=1)
            for j in range(cols):
                frame.columnconfigure(j, weight=1)

        pre = ranges.get("preflop", {})
        post = ranges.get("postflop", {})

        for pos in ["early", "middle", "late"]:
            if pos in pre:
                render_matrix(self.scroll_frame, f"Preflop ({pos})", pre[pos])

        for pos in ["early", "middle", "late"]:
            if pos in post:
                render_matrix(self.scroll_frame, f"Postflop ({pos})", post[pos])

        # Legend
        legend = ttk.Frame(self.scroll_frame)
        legend.pack(fill=tk.X, pady=(6, 2))
        tk.Label(legend, text="Fold", bg="#808080", width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(legend, text="Call", bg="#f0ad4e", width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(legend, text="Raise", bg="#d9534f", width=6).pack(side=tk.LEFT, padx=2)