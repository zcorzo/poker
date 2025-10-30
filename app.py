import threading
import time
import queue
import tkinter as tk
from tkinter import ttk, messagebox

from config import DEFAULT_CONFIG
from ui.views import ConfigView, TournamentView, ResultsView
from tournament.simulator import TournamentSimulator
from ai.training import EvolutionTrainer


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Texas Hold'em Tournament Simulator & Range Optimizer")
        self.geometry("1100x750")

        # State
        self.config_state = DEFAULT_CONFIG.copy()
        self.sim_thread = None
        self.sim_stop_event = threading.Event()
        self.ui_event_queue = queue.Queue()
        self.trainer = EvolutionTrainer()

        # Notebook (tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tabs
        self.config_view = ConfigView(self.notebook, self.config_state, on_apply=self.on_apply_config)
        self.tournament_view = TournamentView(self.notebook, start_cb=self.start_simulation, stop_cb=self.stop_simulation)
        self.results_view = ResultsView(self.notebook)

        self.notebook.add(self.config_view, text="Configuration")
        self.notebook.add(self.tournament_view, text="Tournament")
        self.notebook.add(self.results_view, text="Results")

        # Progress bar and stats
        self.status_frame = ttk.Frame(self)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=6)
        ttk.Label(self.status_frame, text="Optimization progress:").pack(side=tk.LEFT)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(self.status_frame, variable=self.progress_var, maximum=100.0, length=300)
        self.progress.pack(side=tk.LEFT, padx=8)
        self.stats_label = ttk.Label(self.status_frame, text="Idle")
        self.stats_label.pack(side=tk.LEFT, padx=12)

        # UI event loop
        self.after(100, self.process_ui_events)

    def on_apply_config(self, new_cfg: dict):
        self.config_state.update(new_cfg)
        # Update tournament view with new tables/players
        self.tournament_view.build_tables(self.config_state["num_tables"], self.config_state["players_per_table"])
        messagebox.showinfo("Configuration", "Configuration applied.")

    def start_simulation(self):
        if self.sim_thread and self.sim_thread.is_alive():
            messagebox.showwarning("Already running", "Simulation is already running.")
            return

        self.sim_stop_event.clear()
        # Reset trainer if requested
        if self.config_state.get("reset_optimization", False):
            self.trainer.reset()

        # Construct simulator
        simulator = TournamentSimulator(
            config=self.config_state,
            ui_event_queue=self.ui_event_queue,
            stop_event=self.sim_stop_event,
            trainer=self.trainer,
        )

        # Do not rebuild tables here to avoid layout jumping; simulator will emit initial table state
        self.stats_label.config(text="Running...")
        self.progress_var.set(0.0)

        def run():
            try:
                converged, best_ranges = simulator.run_optimization()
                # Prepare results when finished
                self.ui_event_queue.put({
                    "type": "optimization_finished",
                    "converged": converged,
                    "best_ranges": best_ranges
                })
            except Exception as e:
                self.ui_event_queue.put({"type": "error", "error": str(e)})

        self.sim_thread = threading.Thread(target=run, daemon=True)
        self.sim_thread.start()

    def stop_simulation(self):
        if self.sim_thread and self.sim_thread.is_alive():
            self.sim_stop_event.set()
            self.stats_label.config(text="Stopping...")
        else:
            messagebox.showinfo("Not running", "Simulation is not currently running.")

    def process_ui_events(self):
        try:
            while True:
                evt = self.ui_event_queue.get_nowait()
                etype = evt.get("type")

                if etype == "update_tables":
                    # evt: {"type":..., "tables": [[{"id":..., "stack":...}, ...], ...]}
                    self.tournament_view.update_tables(evt["tables"])
                elif etype == "elimination":
                    # {"type":"elimination","player_id":int}
                    self.tournament_view.eliminate_player(evt["player_id"])
                elif etype == "reseat":
                    # {"type":"reseat","tables":[...]}
                    self.tournament_view.update_tables(evt["tables"])
                elif etype == "progress":
                    # {"type":"progress","value": float 0-100, "text": str}
                    val = evt.get("value")
                    if val is not None:
                        self.progress_var.set(val)
                    self.stats_label.config(text=evt.get("text", ""))
                elif etype == "payout_projection":
                    # {"type":"payout_projection","projections":[{"player_id":..,"payout":..}, ...]}
                    projections = evt.get("projections", [])
                    if not projections:
                        self.tournament_view.clear_payouts()
                    else:
                        self.tournament_view.update_payouts(projections)
                elif etype == "best_bankroll":
                    amt = evt.get("amount", 0.0)
                    self.tournament_view.set_best_bankroll(amt)
                elif etype == "optimization_finished":
                    converged = evt.get("converged", False)
                    best_ranges = evt.get("best_ranges", None)
                    self.stats_label.config(text="Converged" if converged else "Stopped")
                    if best_ranges:
                        self.results_view.display_ranges(best_ranges)
                    # Switch to Results tab
                    self.notebook.select(self.results_view)
                elif etype == "error":
                    messagebox.showerror("Error", evt.get("error", "Unknown error"))
                    self.stats_label.config(text="Error")
                else:
                    # ignore unknown event
                    pass
        except queue.Empty:
            pass

        self.after(100, self.process_ui_events)


def main():
    app = App()
    # Build initial tournament tables with defaults
    app.tournament_view.build_tables(DEFAULT_CONFIG["num_tables"], DEFAULT_CONFIG["players_per_table"])
    app.mainloop()


if __name__ == "__main__":
    main()