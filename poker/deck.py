import random
from typing import List, Tuple


RANKS = "23456789TJQKA"
SUITS = "cdhs"  # clubs, diamonds, hearts, spades


class Card:
    __slots__ = ("rank", "suit")

    def __init__(self, rank: str, suit: str):
        self.rank = rank
        self.suit = suit

    def __repr__(self):
        return f"{self.rank}{self.suit}"

    def rank_value(self) -> int:
        return RANKS.index(self.rank)


class Deck:
    def __init__(self, seed=None):
        self.cards: List[Card] = [Card(r, s) for r in RANKS for s in SUITS]
        self.rng = random.Random(seed)

    def shuffle(self):
        self.rng.shuffle(self.cards)

    def deal(self, n=1) -> List[Card]:
        out = self.cards[:n]
        self.cards = self.cards[n:]
        return out

    def reset(self):
        self.cards = [Card(r, s) for r in RANKS for s in SUITS]
        self.shuffle()


def card_tuple(card: Card) -> Tuple[int, str]:
    return (card.rank_value(), card.suit)