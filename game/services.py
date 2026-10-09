import logging
import random
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

logger = logging.getLogger(__name__)

from .models import Bid, Card, PlayedCard, Player, Round, SUITS, TRUMP_SEQUENCE, RANK_VALUES, Trick


def score_for_bid(bid, actual):
    if bid != actual:
        return 0
    return (bid + 1) * 10 + bid


def cards_for_round(player_count, round_number, mode='UP_DOWN', deck_count=1):
    player_count = max(2, player_count)
    d_count = max(1, deck_count)
    total_deck_cards = 52 * d_count
    maximum = max(1, total_deck_cards // player_count)
    if mode == 'UP_DOWN':
        cycle = list(range(1, maximum + 1)) + list(range(maximum - 1, 0, -1))
        return cycle[(round_number - 1) % len(cycle)]
    return min(round_number, maximum)


def get_round_trick_stats(player_count, round_number, mode='UP_DOWN', deck_count=1):
    p_count = max(2, player_count)
    d_count = max(1, deck_count)
    total_deck_cards = 52 * d_count
    cards_per_player = cards_for_round(p_count, round_number, mode, d_count)
    max_hand = max(1, total_deck_cards // p_count)
    total_played = cards_per_player * p_count
    undealt = total_deck_cards - total_played
    return {
        'player_count': p_count,
        'deck_count': d_count,
        'total_deck_cards': total_deck_cards,
        'round_number': round_number,
        'cards_per_player': cards_per_player,
        'max_tricks': cards_per_player,
        'max_hand': max_hand,
        'total_cards_played': total_played,
        'undealt_cards': undealt,
    }


TRUMP_INFO = {
    'SPADES': {'code': 'Ka', 'name': 'Kali', 'symbol': '♠', 'gujarati': 'કાળી', 'display': 'Ka (Kali · ♠ Spades)'},
    'DIAMONDS': {'code': 'Chu', 'name': 'Charkat', 'symbol': '♦', 'gujarati': 'ચોકટ', 'display': 'Chu (Charkat · ♦ Diamonds)'},
    'CLUBS': {'code': 'Fu', 'name': 'Falli', 'symbol': '♣', 'gujarati': 'ફુલ્લી', 'display': 'Fu (Falli · ♣ Clubs)'},
    'HEARTS': {'code': 'L', 'name': 'Lal', 'symbol': '♥', 'gujarati': 'લાલ', 'display': 'L (Lal · ♥ Hearts)'},
}


def trump_for_round(round_number):
    return TRUMP_SEQUENCE[(round_number - 1) % len(TRUMP_SEQUENCE)]


def trump_info_for_round(round_number):
    suit = trump_for_round(round_number)
    info = TRUMP_INFO[suit].copy()
    info['suit'] = suit
    return info


@transaction.atomic
def deal_round(game, number):
    players = list(game.players.all())
    if len(players) < 2:
        raise ValidationError('A game needs at least 2 players.')
    amount = cards_for_round(len(players), number, game.round_mode, game.deck_count)
    round_obj = Round.objects.create(game=game, number=number, cards_per_player=amount, trump_suit=trump_for_round(number), status=Round.Status.BIDDING)
    single_deck = [(suit, rank) for suit, _ in SUITS for rank in RANK_VALUES]
    deck = single_deck * max(1, game.deck_count)
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


import string
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.auth.models import User


def generate_zomato_coupon():
    random_digits = ''.join(random.choices(string.digits, k=6))
    return f"ZOMATO-WIN-{random_digits}"


def award_game_finish_points(player_list):
    """
    Awards Kachhuful Reward Points to players based on final standings:
    - 1st Place: +10 Points
    - 2nd Place: +5 Points
    - 3rd Place (if total players > 5): +3 Points
    """
    valid_players = [p for p in player_list if p.get('name')]
    if not valid_players:
        return

    sorted_players = sorted(valid_players, key=lambda x: int(x.get('score', 0)), reverse=True)
    player_count = len(sorted_players)
    if player_count < 1:
        return

    unique_scores = sorted(list(set(int(p.get('score', 0)) for p in sorted_players)), reverse=True)
    rank1_score = unique_scores[0] if len(unique_scores) > 0 else None
    rank2_score = unique_scores[1] if len(unique_scores) > 1 else None
    rank3_score = unique_scores[2] if len(unique_scores) > 2 else None

    from .models import UserReward
    for p in valid_players:
        name = p.get('name')
        if not name:
            continue

        score = int(p.get('score', 0))
        pts_to_award = 0

        if score == rank1_score and score > 0:
            pts_to_award = 10
        elif score == rank2_score:
            pts_to_award = 5
        elif player_count > 5 and score == rank3_score:
            pts_to_award = 3

        if pts_to_award > 0:
            user_match = User.objects.filter(first_name__iexact=name).first() or User.objects.filter(username__iexact=name).first()
            if not user_match and p.get('email'):
                user_match = User.objects.filter(email__iexact=p.get('email')).first()

            if user_match:
                reward, _ = UserReward.objects.get_or_create(user=user_match)
                reward.points += pts_to_award
                reward.total_points_earned += pts_to_award
                reward.save()


def save_game_rounds_and_scores(game, player_list, rounds_list, deck_count=None):
    """
    Saves players, round-by-round bids, actual tricks, and scores to the database for a Game.
    """
    if deck_count:
        game.deck_count = int(deck_count)
        game.save(update_fields=['deck_count'])

    player_map = {}
    for idx, pdata in enumerate(player_list):
        p_name = pdata.get('name', '').strip()
        if not p_name:
            continue
        p_score = int(pdata.get('score', 0))
        p_email = pdata.get('email', '').strip()

        p_obj = game.players.filter(name__iexact=p_name).first()
        if not p_obj:
            p_obj = Player.objects.create(game=game, name=p_name, email=p_email, seat=idx + 1, score=p_score)
        else:
            p_obj.score = p_score
            if p_email:
                p_obj.email = p_email
            p_obj.save()
        player_map[p_name.lower()] = p_obj

    max_round_num = 0
    for rdata in rounds_list:
        r_num = int(rdata.get('number', 1))
        if r_num > max_round_num:
            max_round_num = r_num
        cards_per_player = int(rdata.get('cards_per_player', 1))
        trump_suit = str(rdata.get('trump_suit', 'SPADES')).upper()
        phase = str(rdata.get('phase', '3'))

        r_status = Round.Status.COMPLETE if phase == '3' else (Round.Status.PLAYING if phase == '2' else Round.Status.BIDDING)

        r_obj = game.rounds.filter(number=r_num).first()
        if not r_obj:
            r_obj = Round.objects.create(
                game=game,
                number=r_num,
                cards_per_player=cards_per_player,
                trump_suit=trump_suit,
                status=r_status
            )
        else:
            r_obj.cards_per_player = cards_per_player
            r_obj.trump_suit = trump_suit
            r_obj.status = r_status
            r_obj.save()

        bids_list = rdata.get('bids', [])
        Trick.objects.filter(round=r_obj).delete()
        trick_counter = 1
        for bdata in bids_list:
            p_name = bdata.get('player_name', '').strip()
            p_obj = player_map.get(p_name.lower())
            if not p_obj:
                p_obj = game.players.filter(name__iexact=p_name).first()
            if not p_obj:
                continue

            bid_amt = int(bdata.get('bid', 0))
            actual_tricks = int(bdata.get('actual', 0))

            b_obj = Bid.objects.filter(round=r_obj, player=p_obj).first()
            if not b_obj:
                b_obj = Bid.objects.create(round=r_obj, player=p_obj, amount=bid_amt, actual_tricks=actual_tricks)
            else:
                b_obj.amount = bid_amt
                b_obj.actual_tricks = actual_tricks
                b_obj.save()

            for _ in range(actual_tricks):
                Trick.objects.create(
                    round=r_obj,
                    number=trick_counter,
                    leader=p_obj,
                    winner=p_obj
                )
                trick_counter += 1

    if max_round_num > 0:
        game.current_round = max_round_num
        game.save(update_fields=['current_round'])


def send_game_finished_emails(game_name, player_list, award_points=True):
    """
    player_list: list of dicts: [{'name': '...', 'email': '...', 'score': 100}, ...]
    Identifies ALL winners (highest score, handles ties) and ALL losers (lowest score, handles ties).
    Sends Champion Victory email to Winners, and Better Luck Next Time email to Losers.
    Also awards Kachhuful Reward Points (+10 for 1st, +5 for 2nd, +3 for 3rd if >5 players).
    """
    if award_points:
        award_game_finish_points(player_list)
    valid_players = [p for p in player_list if p.get('name')]
    if not valid_players:
        return {'winners_sent': 0, 'losers_sent': 0}

    scores = [int(p.get('score', 0)) for p in valid_players]
    max_score = max(scores)
    min_score = min(scores)

    # Ties handling: Everyone with score == max_score is a WINNER!
    winners = [p for p in valid_players if int(p.get('score', 0)) == max_score]

    # Ties handling: Everyone with score == min_score (where min_score < max_score) is a LOSER!
    losers = [p for p in valid_players if int(p.get('score', 0)) == min_score and min_score < max_score]

    winners_sent = 0
    losers_sent = 0

    # 1. Send Winner Emails
    for winner in winners:
        name = winner.get('name')
        email = winner.get('email', '').strip()

        if not email:
            user_match = User.objects.filter(first_name__iexact=name).first() or User.objects.filter(username__iexact=name).first()
            if user_match and user_match.email:
                email = user_match.email

        if email:
            html_content = render_to_string('emails/winner_email.html', {
                'player_name': name,
                'player_email': email,
                'player_score': winner.get('score', max_score),
                'game_name': game_name,
            })
            text_content = f"CONGRATULATIONS {name}! You WON 1st Place at {game_name} with {winner.get('score', max_score)} points! You are the Kachhu Ful Champion!"

            from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'dhruvtt042@tesseracttechnolabs.com'
            msg = EmailMultiAlternatives(
                subject=f"🏆 YOU WON! 🥇 Champion Victory at {game_name}",
                body=text_content,
                from_email=from_addr,
                to=[email]
            )
            msg.attach_alternative(html_content, "text/html")
            try:
                msg.send(fail_silently=False)
                winners_sent += 1
            except Exception as e:
                logger.error("Error sending winner email to %s: %s", email, str(e).encode('ascii', 'ignore').decode('ascii'))

    # 2. Send Loser Emails
    for loser in losers:
        name = loser.get('name')
        email = loser.get('email', '').strip()

        if not email:
            user_match = User.objects.filter(first_name__iexact=name).first() or User.objects.filter(username__iexact=name).first()
            if user_match and user_match.email:
                email = user_match.email

        if email:
            html_content = render_to_string('emails/loser_email.html', {
                'player_name': name,
                'player_email': email,
                'player_score': loser.get('score', min_score),
                'game_name': game_name,
            })
            text_content = f"Hi {name}, better luck next time! You played hard at {game_name} with {loser.get('score', min_score)} pts. Keep practicing your bids!"

            from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'dhruvtt042@tesseracttechnolabs.com'
            msg = EmailMultiAlternatives(
                subject=f"👎 Better Luck Next Time, {name}! - Kachhu Ful",
                body=text_content,
                from_email=from_addr,
                to=[email]
            )
            msg.attach_alternative(html_content, "text/html")
            try:
                msg.send(fail_silently=False)
                losers_sent += 1
            except Exception as e:
                logger.error("Error sending loser email to %s: %s", email, str(e).encode('ascii', 'ignore').decode('ascii'))

    return {
        'winners_sent': winners_sent,
        'losers_sent': losers_sent,
        'max_score': max_score,
        'min_score': min_score,
        'winners_count': len(winners),
        'losers_count': len(losers),
    }

