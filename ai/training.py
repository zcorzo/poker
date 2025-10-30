import random
from typing import List, Dict, Optional

try:
    import torch
    import torch.nn as nn
except Exception:
    torch = None
    nn = None

from ai.genome import Genome


class SimpleRangeNet(nn.Module):
    """
    A minimal network mapping genome features to a scalar performance estimate.
    This is a placeholder; in a full implementation, you'd encode hand combos,
    positions, stack sizes, and board textures.
    """
    def __init__(self, input_dim=100, hidden=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x):
        return self.net(x)


class EvolutionTrainer:
    def __init__(self, population_size: int = 100, elite_fraction: float = 0.1, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.population_size = population_size
        self.elite_fraction = elite_fraction
        self.population: List[Genome] = [Genome(seed=self.rng.randint(0, 1_000_000)) for _ in range(population_size)]
        self.history: List[Dict] = []
        self.model = SimpleRangeNet() if torch and nn else None
        if torch and nn:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)
        else:
            self.optimizer = None

    def reset(self):
        self.population = [Genome(seed=self.rng.randint(0, 1_000_000)) for _ in range(self.population_size)]
        self.history = []

    def encode_genome(self, g: Genome) -> List[float]:
        # Flatten matrices and scalars to a fixed-length vector, truncated/padded to 100
        vec = []
        for d in [g.preflop, g.postflop]:
            for pos in ["early", "middle", "late"]:
                mat = d[pos]
                for row in mat:
                    vec.extend(row)
        vec.extend([g.aggression, g.bluff_freq, g.value_freq])
        # Normalize length
        if len(vec) < 100:
            vec += [0.0] * (100 - len(vec))
        else:
            vec = vec[:100]
        return vec

    def estimate_fitness(self, genomes: List[Genome]) -> List[float]:
        # If torch available, use the network to estimate; otherwise random fitness
        if self.model:
            self.model.train()
            x = torch.tensor([self.encode_genome(g) for g in genomes], dtype=torch.float32)
            y = self.model(x).squeeze().detach().numpy().tolist()
            return y
        else:
            return [self.rng.random() for _ in genomes]

    def evolve(self, survivors: List[Genome]) -> None:
        # Combine survivors with new random genomes, mutate and crossover to refill population
        elite = survivors[:max(1, int(self.elite_fraction * self.population_size))]
        new_pop = []
        # Keep elites
        new_pop.extend(elite)
        # Crossover between elites to create children
        while len(new_pop) < self.population_size:
            a = self.rng.choice(elite)
            b = self.rng.choice(elite)
            child = a.crossover(b)
            child.mutate(rate=0.1, scale=0.05)
            new_pop.append(child)
        self.population = new_pop

    def check_convergence(self, window: int, eps: float) -> bool:
        # Check average variance of recent elite genomes' parameters as a proxy convergence metric
        if len(self.history) < window:
            return False
        recent = self.history[-window:]
        # Compute average fitness spread
        spreads = [h["fitness_spread"] for h in recent]
        avg_spread = sum(spreads) / len(spreads)
        return avg_spread < eps

    def best_ranges(self) -> Dict:
        # Return ranges from the top genome in last history entry
        if not self.history:
            return self.population[0].to_dict()
        best = self.history[-1]["elite"][0]
        return best.to_dict()

    def rank_population(self) -> Dict:
        """
        Rank current population without evolving it. Records fitness spread and elites to history.
        """
        fitness = self.estimate_fitness(self.population)
        ranked = sorted(zip(self.population, fitness), key=lambda x: x[1], reverse=True)
        elite_genomes = [g for g, f in ranked[:max(1, int(self.elite_fraction * len(ranked)))]]
        fitness_spread = max(fitness) - min(fitness) if fitness else 1.0
        info = {
            "elite": elite_genomes,
            "fitness_spread": fitness_spread,
            "best_fitness": max(fitness) if fitness else 0.0,
        }
        self.history.append(info)
        return info