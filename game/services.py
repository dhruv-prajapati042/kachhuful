import random
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Bid, Card, PlayedCard, Round, SUITS, TRUMP_SEQUENCE, RANK_VALUES, Trick


def score_for_bid(bid, actual):
    if bid != actual:
        return 0
    return (bid + 1) * 10 + bid


def cards_for_round(player_count, round_number, mode='UP_DOWN'):
    maximum = max(1, 52 // player_count)
    if mode == 'UP_DOWN':
        cycle = list(range(1, maximum + 1)) + list(range(maximum - 1, 0, -1))
        return cycle[(round_number - 1) % len(cycle)]
    return min(round_number, maximum)


def trump_for_round(round_number):
    return TRUMP_SEQUENCE[(round_number - 1) % len(TRUMP_SEQUENCE)]


@transaction.atomic
def deal_round(game, number):
    players = list(game.players.all())
    if not 3 <= len(players) <= 8:
        raise ValidationError('A game needs between 3 and 8 players.')
    amount = cards_for_round(len(players), number, game.round_mode)
    round_obj = Round.objects.create(game=game, number=number, cards_per_player=amount, trump_suit=trump_for_round(number), status=Round.Status.BIDDING)
    deck = [(suit, rank) for suit, _ in SUITS for rank in RANK_VALUES]
    random.shuffle(deck)
    for index, player in enumerate(players):
        for suit, rank in deck[index * amount:(index + 1) * amount]:
            Card.objects.create(round=round_obj, player=player, suit=suit, rank=rank)
    round_obj.leader = players[(number - 1) % len(players)]
    round_obj.current_player = round_obj.leader
    round_obj.save(update_fields=['leader', 'current_player'])
    return round_obj


def valid_card_ids(trick, player):
    hand = Card.objects.filter(round=trick.round, player=player, is_played=False)
    if not trick.lead_suit:
        return set(hand.values_list('id', flat=True))
    has_lead = hand.filter(suit=trick.lead_suit).exists()
    candidates = hand.filter(suit=trick.lead_suit) if has_lead else hand
    return set(candidates.values_list('id', flat=True))


def winner_for_trick(trick):
    plays = list(trick.plays.select_related('card', 'player'))
    if not plays:
        return None
    trump_plays = [play for play in plays if play.card.suit == trick.round.trump_suit]
    candidates = trump_plays or [play for play in plays if play.card.suit == trick.lead_suit]
    return max(candidates, key=lambda play: RANK_VALUES[play.card.rank]).player


@transaction.atomic
def submit_bid(round_obj, player, amount):
    bid = Bid(round=round_obj, player=player, amount=amount)
    bid.full_clean()
    bid.save()
    if round_obj.bids.count() == round_obj.game.players.count():
        round_obj.status = Round.Status.PLAYING
        round_obj.save(update_fields=['status'])
    return bid


@transaction.atomic
def play_card(round_obj, player, card_id):
    if round_obj.status != Round.Status.PLAYING:
        raise ValidationError('Cards can only be played during the playing phase.')
    if round_obj.current_player_id != player.id:
        raise ValidationError('It is not your turn.')
    trick = round_obj.tricks.filter(winner__isnull=True).order_by('number').last()
    if trick is None:
        trick = Trick.objects.create(round=round_obj, number=round_obj.tricks.count() + 1, leader=player)
    card = Card.objects.filter(id=card_id, round=round_obj, player=player, is_played=False).first()
    if card is None:
        raise ValidationError('That card is not in your hand.')
    if card.id not in valid_card_ids(trick, player):
        raise ValidationError('You must follow the lead suit when possible.')
    if not trick.lead_suit:
        trick.lead_suit = card.suit
        trick.save(update_fields=['lead_suit'])
    card.is_played = True
    card.save(update_fields=['is_played'])
    PlayedCard.objects.create(trick=trick, player=player, card=card)
    players = list(round_obj.game.players.all())
    next_index = (players.index(player) + 1) % len(players)
    if trick.plays.count() < len(players):
        round_obj.current_player = players[next_index]
        round_obj.save(update_fields=['current_player'])
    else:
        winner = winner_for_trick(trick)
        trick.winner = winner
        trick.save(update_fields=['winner'])
        winner.tricks_won = winner.tricks_won + 1
        winner.save(update_fields=['tricks_won'])
        played_tricks = round_obj.tricks.filter(winner__isnull=False).count()
        if played_tricks >= round_obj.cards_per_player:
            for bid in round_obj.bids.select_related('player'):
                actual = round_obj.tricks.filter(winner=bid.player).count()
                bid.player.score += score_for_bid(bid.amount, actual)
                bid.player.save(update_fields=['score'])
            round_obj.status = Round.Status.COMPLETE
            round_obj.save(update_fields=['status'])
        else:
            round_obj.current_player = winner
            round_obj.save(update_fields=['current_player'])
    return card
