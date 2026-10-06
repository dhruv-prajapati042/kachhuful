from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Bid, Card, Game, Player, Round, Trick
from .services import deal_round, play_card, score_for_bid, trump_for_round, trump_info_for_round


class GameRulesTests(TestCase):
	def setUp(self):
		self.game = Game.objects.create(name='Test table', dealer_restriction=True)
		for seat in range(1, 5):
			Player.objects.create(game=self.game, name=f'Player {seat}', seat=seat, is_dealer=seat == 4)

	def test_trump_rotates_in_kachhu_ful_order(self):
		self.assertEqual([trump_for_round(number) for number in range(1, 5)], ['SPADES', 'DIAMONDS', 'CLUBS', 'HEARTS'])
		self.assertEqual([trump_info_for_round(number)['code'] for number in range(1, 5)], ['Ka', 'Chu', 'Fu', 'L'])
		self.assertEqual(trump_info_for_round(5)['code'], 'Ka')

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

	def test_get_round_trick_stats(self):
		from .services import get_round_trick_stats
		stats_5p = get_round_trick_stats(5, 10)
		self.assertEqual(stats_5p['cards_per_player'], 10)
		self.assertEqual(stats_5p['max_tricks'], 10)
		self.assertEqual(stats_5p['total_cards_played'], 50)
		self.assertEqual(stats_5p['undealt_cards'], 2)

		stats_4p = get_round_trick_stats(4, 13)
		self.assertEqual(stats_4p['cards_per_player'], 13)
		self.assertEqual(stats_4p['max_tricks'], 13)
		self.assertEqual(stats_4p['total_cards_played'], 52)
		self.assertEqual(stats_4p['undealt_cards'], 0)

		stats_2decks_5p = get_round_trick_stats(5, 20, deck_count=2)
		self.assertEqual(stats_2decks_5p['total_deck_cards'], 104)
		self.assertEqual(stats_2decks_5p['max_hand'], 20)
		self.assertEqual(stats_2decks_5p['cards_per_player'], 20)
		self.assertEqual(stats_2decks_5p['max_tricks'], 20)
		self.assertEqual(stats_2decks_5p['total_cards_played'], 100)
		self.assertEqual(stats_2decks_5p['undealt_cards'], 4)

	def test_send_game_finished_emails_single_winner_loser(self):
		from django.core import mail
		from .services import send_game_finished_emails
		players = [
			{'name': 'Alice', 'email': 'alice@example.com', 'score': 150},
			{'name': 'Bob', 'email': 'bob@example.com', 'score': 90},
			{'name': 'Charlie', 'email': 'charlie@example.com', 'score': 30},
		]
		result = send_game_finished_emails('Championship', players)
		self.assertEqual(result['winners_count'], 1)
		self.assertEqual(result['losers_count'], 1)
		self.assertEqual(result['winners_sent'], 1)
		self.assertEqual(result['losers_sent'], 1)
		self.assertEqual(len(mail.outbox), 2)
		
		# Check Winner Email
		winner_mail = mail.outbox[0] if 'YOU WON' in mail.outbox[0].subject else mail.outbox[1]
		self.assertIn('alice@example.com', winner_mail.to)
		self.assertIn('CONGRATULATIONS', winner_mail.body)
		self.assertIn('Champion Victory', winner_mail.subject)

		# Check Loser Email
		loser_mail = mail.outbox[1] if winner_mail == mail.outbox[0] else mail.outbox[0]
		self.assertIn('charlie@example.com', loser_mail.to)
		self.assertIn('Better Luck Next Time', loser_mail.subject)

	def test_send_game_finished_emails_tied_winners_and_losers(self):
		from django.core import mail
		from .services import send_game_finished_emails
		players = [
			{'name': 'Alice', 'email': 'alice@example.com', 'score': 200},
			{'name': 'Bob', 'email': 'bob@example.com', 'score': 200},
			{'name': 'Charlie', 'email': 'charlie@example.com', 'score': 50},
			{'name': 'David', 'email': 'david@example.com', 'score': 50},
		]
		result = send_game_finished_emails('Tie Match', players)
		self.assertEqual(result['winners_count'], 2)
		self.assertEqual(result['losers_count'], 2)
		self.assertEqual(result['winners_sent'], 2)
		self.assertEqual(result['losers_sent'], 2)
		self.assertEqual(len(mail.outbox), 4)

	def test_award_game_finish_points(self):
		from django.contrib.auth.models import User
		from .models import UserReward
		from .services import send_game_finished_emails
		u1 = User.objects.create_user(username='winner_user', first_name='WinnerUser')
		u2 = User.objects.create_user(username='runner_user', first_name='RunnerUser')
		players = [
			{'name': 'WinnerUser', 'score': 100},
			{'name': 'RunnerUser', 'score': 50},
		]
		send_game_finished_emails('Points Test Game', players)
		r1 = UserReward.objects.get(user=u1)
		r2 = UserReward.objects.get(user=u2)
		self.assertEqual(r1.points, 10)  # 1st Place = +10
		self.assertEqual(r2.points, 5)   # 2nd Place = +5

	def test_daily_login_streak_cycle(self):
		from django.contrib.auth.models import User
		from .models import UserReward
		from .context_processors import check_daily_login_reward
		from datetime import timedelta
		from django.utils import timezone
		u = User.objects.create_user(username='streak_user')
		res1 = check_daily_login_reward(u)
		self.assertEqual(res1['points_added'], 1)  # Day 1 = +1
		self.assertEqual(res1['streak_day'], 1)

		# Simulate consecutive login next day
		r = UserReward.objects.get(user=u)
		r.last_login_date = timezone.localdate() - timedelta(days=1)
		r.streak_days = 6
		r.save()

		res7 = check_daily_login_reward(u)
		self.assertEqual(res7['points_added'], 7)  # Day 7 = +7
		self.assertEqual(res7['streak_day'], 7)

	def test_redeem_points_threshold(self):
		from django.contrib.auth.models import User
		from .models import UserReward
		u = User.objects.create_user(username='rich_user')
		r = UserReward.objects.create(user=u, points=105)
		self.client.force_login(u)
		response = self.client.post('/redeem-points/')
		self.assertEqual(response.status_code, 200)
		r.refresh_from_db()
		self.assertEqual(r.points, 5)  # 105 - 100 = 5
		self.assertEqual(r.total_points_redeemed, 100)


