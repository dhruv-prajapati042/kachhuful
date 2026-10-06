from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Bid, Card, Game, Player, Round, Trick
from .services import deal_round, play_card, score_for_bid, trump_for_round


class GameRulesTests(TestCase):
	def setUp(self):
		self.game = Game.objects.create(name='Test table', dealer_restriction=True)
		for seat in range(1, 5):
			Player.objects.create(game=self.game, name=f'Player {seat}', seat=seat, is_dealer=seat == 4)

	def test_trump_rotates_in_kachhu_ful_order(self):
		self.assertEqual([trump_for_round(number) for number in range(1, 5)], ['SPADES', 'DIAMONDS', 'CLUBS', 'HEARTS'])

	def test_exact_bid_scoring(self):
		self.assertEqual(score_for_bid(0, 0), 10)
		self.assertEqual(score_for_bid(1, 1), 21)
		self.assertEqual(score_for_bid(3, 3), 43)
		self.assertEqual(score_for_bid(3, 2), 0)

	def test_round_deals_equal_hands(self):
		round_obj = deal_round(self.game, 1)
		self.assertEqual(round_obj.cards_per_player, 1)
		self.assertEqual(round_obj.cards.count(), 4)

	def test_dealer_cannot_make_total_equal_tricks(self):
		round_obj = deal_round(self.game, 1)
		for player, amount in zip(self.game.players.all()[:3], [0, 0, 0]):
			Bid.objects.create(round=round_obj, player=player, amount=amount)
		with self.assertRaises(ValidationError):
			Bid(round=round_obj, player=self.game.players.get(seat=4), amount=1).full_clean()

	def test_player_must_follow_lead_suit(self):
		round_obj = Round.objects.create(game=self.game, number=1, cards_per_player=1, trump_suit='HEARTS', status=Round.Status.PLAYING)
		leader, player = self.game.players.all()[:2]
		round_obj.current_player = leader
		round_obj.leader = leader
		round_obj.save()
		trick = Trick.objects.create(round=round_obj, number=1, leader=leader, lead_suit='CLUBS')
		Card.objects.create(round=round_obj, player=player, suit='CLUBS', rank='2')
		Card.objects.create(round=round_obj, player=player, suit='HEARTS', rank='A')
		round_obj.current_player = player
		round_obj.save()
		with self.assertRaises(ValidationError):
			play_card(round_obj, player, Card.objects.get(player=player, suit='HEARTS').id)
