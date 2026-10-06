from django.core.exceptions import ValidationError
from django.db import models


SUITS = [('SPADES', 'Spades'), ('DIAMONDS', 'Diamonds'), ('CLUBS', 'Clubs'), ('HEARTS', 'Hearts')]
RANKS = [('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), ('6', '6'), ('7', '7'), ('8', '8'), ('9', '9'), ('10', '10'), ('J', 'Jack'), ('Q', 'Queen'), ('K', 'King'), ('A', 'Ace')]
TRUMP_SEQUENCE = ['SPADES', 'DIAMONDS', 'CLUBS', 'HEARTS']
RANK_VALUES = {rank: value for value, (rank, _) in enumerate(RANKS, start=2)}


class Game(models.Model):
	class Status(models.TextChoices):
		WAITING = 'WAITING', 'Waiting for players'
		BIDDING = 'BIDDING', 'Bidding'
		PLAYING = 'PLAYING', 'Playing'
		FINISHED = 'FINISHED', 'Finished'

	name = models.CharField(max_length=120)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
	dealer_restriction = models.BooleanField(default=True)
	round_mode = models.CharField(max_length=20, default='UP_DOWN')
	deck_count = models.PositiveSmallIntegerField(default=1)
	current_round = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.name


class Player(models.Model):
	game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='players')
	name = models.CharField(max_length=80)
	email = models.EmailField(max_length=120, blank=True, default='')
	seat = models.PositiveSmallIntegerField()
	score = models.IntegerField(default=0)
	tricks_won = models.PositiveSmallIntegerField(default=0)
	is_dealer = models.BooleanField(default=False)

	class Meta:
		
		ordering = ['seat']
		constraints = [models.UniqueConstraint(fields=['game', 'seat'], name='unique_game_seat')]

	def __str__(self):
		return f'{self.name} ({self.game.name})'


class Round(models.Model):
	class Status(models.TextChoices):
		DEALING = 'DEALING', 'Dealing'
		BIDDING = 'BIDDING', 'Bidding'
		PLAYING = 'PLAYING', 'Playing'
		COMPLETE = 'COMPLETE', 'Complete'

	game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='rounds')
	number = models.PositiveSmallIntegerField()
	cards_per_player = models.PositiveSmallIntegerField()
	trump_suit = models.CharField(max_length=10, choices=SUITS)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DEALING)
	leader = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name='led_rounds')
	current_player = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name='turns')

	class Meta:
		constraints = [models.UniqueConstraint(fields=['game', 'number'], name='unique_game_round')]

	def __str__(self):
		return f'{self.game.name} · Round {self.number}'


class Card(models.Model):
	round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='cards')
	player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='cards')
	suit = models.CharField(max_length=10, choices=SUITS)
	rank = models.CharField(max_length=2, choices=RANKS)
	is_played = models.BooleanField(default=False)

	class Meta:
		constraints = [models.UniqueConstraint(fields=['round', 'suit', 'rank'], name='unique_round_card')]

	def __str__(self):
		return f'{self.rank} of {self.get_suit_display()} · {self.player.name}'


class Bid(models.Model):
	round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='bids')
	player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='bids')
	amount = models.PositiveSmallIntegerField()
	submitted_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [models.UniqueConstraint(fields=['round', 'player'], name='unique_round_bid')]

	def __str__(self):
		return f'{self.player.name} · {self.round} · Bid {self.amount}'

	def clean(self):
		if self.amount > self.round.cards_per_player:
			raise ValidationError('A bid cannot exceed the number of cards in the round.')
		if self.round.game.dealer_restriction and self.player.is_dealer:
			previous_total = self.round.bids.exclude(player=self.player).aggregate(total=models.Sum('amount'))['total'] or 0
			if previous_total + self.amount == self.round.cards_per_player:
				raise ValidationError('The dealer cannot make the total bids equal the number of tricks.')


class Trick(models.Model):
	round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='tricks')
	number = models.PositiveSmallIntegerField()
	leader = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='led_tricks')
	winner = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name='won_tricks')
	lead_suit = models.CharField(max_length=10, choices=SUITS, blank=True)

	class Meta:
		constraints = [models.UniqueConstraint(fields=['round', 'number'], name='unique_round_trick')]

	def __str__(self):
		return f'{self.round} · Trick {self.number}'


class PlayedCard(models.Model):
	trick = models.ForeignKey(Trick, on_delete=models.CASCADE, related_name='plays')
	player = models.ForeignKey(Player, on_delete=models.PROTECT)
	card = models.ForeignKey(Card, on_delete=models.PROTECT)
	played_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['played_at']
		constraints = [models.UniqueConstraint(fields=['trick', 'player'], name='one_card_per_player_trick')]

	def __str__(self):
		return f'{self.player.name} played {self.card}'


from django.contrib.auth.models import User


class UserReward(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='reward')
	points = models.PositiveIntegerField(default=0)
	streak_days = models.PositiveSmallIntegerField(default=0)
	last_login_date = models.DateField(null=True, blank=True)
	total_points_earned = models.PositiveIntegerField(default=0)
	total_points_redeemed = models.PositiveIntegerField(default=0)

	def __str__(self):
		return f'{self.user.username} - {self.points} Points (Day {self.streak_days} Streak)'
