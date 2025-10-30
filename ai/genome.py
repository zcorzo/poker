import random
from typing import Dict, List
from uuid import uuid4


class Genome:
    """
    Represents a player's betting ranges and strategy parameters.
    - Preflop ranges: matrices for early/middle/late positions (13x13 for combos, simplified here to 13x13 values)
    - Postflop ranges: matrices for early/middle/late positions (e.g., 5x5 buckets representing aggression levels)
    """

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.uid = str(uuid4())
        self.preflop = {
            "early": self.random_matrix(13, 13),
            "middle": self.random_matrix(13, 13),
            "late": self.random_matrix(13, 13),
        }
        self.postflop = {
            "early": self.random_matrix(5, 5),
            "middle": self.random_matrix(5, 5),
            "late": self.random_matrix(5, 5),
        }
        # Example scalar parameters
        self.aggression = self.rng.uniform(0.3, 0.7)
        self.bluff_freq = self.rng.uniform(0.1, 0.3)
        self.value_freq = self.rng.uniform(0.3, 0.7)

    def random_matrix(self, rows: int, cols: int) -> List[List[float]]:
        return [[self.rng.random() for _ in range(cols)] for _ in range(rows)]

    def mutate(self, rate=0.05, scale=0.1):
        for d in [self.preflop, self.postflop]:
            for pos, mat in d.items():
                for i in range(len(mat)):
                    for j in range(len(mat[i])):
                        if self.rng.random() < rate:
                            delta = self.rng.uniform(-scale, scale)
                            mat[i][j] = min(1.0, max(0.0, mat[i][j] + delta))
        # mutate scalars
        for attr in ["aggression", "bluff_freq", "value_freq"]:
            if self.rng.random() < rate:
                delta = self.rng.uniform(-scale, scale)
                v = getattr(self, attr)
                setattr(self, attr, min(1.0, max(0.0, v + delta)))

    def crossover(self, other: "Genome") -> "Genome":
        child = Genome()
        def mix(a, b):
            return (a + b) / 2.0
        for dname in ["preflop", "postflop"]:
            d_self = getattr(self, dname)
            d_other = getattr(other, dname)
            child_dict = {}
            for pos in d_self.keys():
                mat_self = d_self[pos]
                mat_other = d_other[pos]
                child_dict[pos] = [[mix(mat_self[i][j], mat_other[i][j]) for j in range(len(mat_self[i]))] for i in range(len(mat_self))]
            setattr(child, dname, child_dict)
        child.aggression = mix(self.aggression, other.aggression)
        child.bluff_freq = mix(self.bluff_freq, other.bluff_freq)
        child.value_freq = mix(self.value_freq, other.value_freq)
        return child

    def to_dict(self) -> Dict:
        return {
            "uid": self.uid,
            "preflop": self.preflop,
            "postflop": self.postflop,
            "aggression": self.aggression,
            "bluff_freq": self.bluff_freq,
            "value_freq": self.value_freq,
        }