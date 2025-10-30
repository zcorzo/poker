from typing import List, Tuple
from collections import Counter

from poker.deck import Card, RANKS


# Simple 7-card evaluator for Texas Hold'em
# Returns a tuple (category_rank, tiebreaker list) where higher is better.
# Categories (low->high):
# 0: High Card
# 1: One Pair
# 2: Two Pair
# 3: Three of a Kind
# 4: Straight
# 5: Flush
# 6: Full House
# 7: Four of a Kind
# 8: Straight Flush


def rank_value(card: Card) -> int:
    return RANKS.index(card.rank)


def is_straight(rank_counts: Counter) -> Tuple[bool, List[int]]:
    ranks = sorted(set(rank_counts.keys()))
    # Handle Ace-low straight
    if 12 in ranks:  # Ace index
        ranks = [0] + ranks  # treat Ace as 1 for low straight possibility

    longest = []
    streak = [ranks[0]] if ranks else []
    for i in range(1, len(ranks)):
        if ranks[i] == ranks[i - 1] + 1:
            streak.append(ranks[i])
        else:
            if len(streak) >= 5:
                longest = streak
            streak = [ranks[i]]
    if len(streak) >= 5:
        longest = streak

    if len(longest) >= 5:
        return True, longest[-5:]
    return False, []


def is_flush(cards: List[Card]) -> Tuple[bool, List[int], str]:
    suit_groups = {}
    for c in cards:
        suit_groups.setdefault(c.suit, []).append(c)
    for suit, group in suit_groups.items():
        if len(group) >= 5:
            ranks = sorted([rank_value(c) for c in group], reverse=True)
            return True, ranks[:5], suit
    return False, [], ""


def best_hand_7(cards: List[Card]) -> Tuple[int, List[int]]:
    ranks = [rank_value(c) for c in cards]
    rank_counts = Counter(ranks)
    is_str, str_cards = is_straight(rank_counts)
    is_fl, fl_cards, fl_suit = is_flush(cards)

    # Straight flush
    if is_fl:
        # compute straight in the flush suit
        fl_only = [c for c in cards if c.suit == fl_suit]
        fl_ranks = Counter([rank_value(c) for c in fl_only])
        is_sf, sf_cards = is_straight(fl_ranks)
        if is_sf:
            return 8, sorted(sf_cards, reverse=True)

    # Four of a kind
    fours = [r for r, cnt in rank_counts.items() if cnt == 4]
    if fours:
        four = max(fours)
        kicker = max([r for r in ranks if r != four])
        return 7, [four, kicker]

    # Full house
    trips = sorted([r for r, cnt in rank_counts.items() if cnt == 3], reverse=True)
    pairs = sorted([r for r, cnt in rank_counts.items() if cnt == 2], reverse=True)
    if trips and (pairs or len(trips) >= 2):
        trip = trips[0]
        if len(trips) >= 2:
            pair = trips[1]
        else:
            pair = pairs[0]
        return 6, [trip, pair]

    # Flush
    if is_fl:
        return 5, fl_cards

    # Straight
    if is_str:
        return 4, sorted(str_cards, reverse=True)

    # Three of a kind
    if trips:
        trip = trips[0]
        kickers = sorted([r for r in ranks if r != trip], reverse=True)[:2]
        return 3, [trip] + kickers

    # Two pair
    if len(pairs) >= 2:
        p1, p2 = pairs[:2]
        kicker = max([r for r in ranks if r != p1 and r != p2])
        return 2, [p1, p2, kicker]

    # One pair
    if len(pairs) == 1:
        p = pairs[0]
        kickers = sorted([r for r in ranks if r != p], reverse=True)[:3]
        return 1, [p] + kickers

    # High card
    return 0, sorted(ranks, reverse=True)[:5]


def compare_hands(cards_a: List[Card], cards_b: List[Card], board: List[Card]) -> int:
    """Return 1 if A wins, -1 if B wins, 0 if tie."""
    ra = best_hand_7(cards_a + board)
    rb = best_hand_7(cards_b + board)
    if ra[0] != rb[0]:
        return 1 if ra[0] > rb[0] else -1
    # tiebreaker comparison
    for a, b in zip(ra[1], rb[1]):
        if a != b:
            return 1 if a > b else -1
    return 0