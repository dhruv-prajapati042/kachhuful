from django.contrib import admin

from .models import Bid, Card, Game, PlayedCard, Player, Round, Trick


class PlayerInline(admin.TabularInline):
	model = Player
	extra = 0
	fields = ('name', 'seat', 'score', 'tricks_won', 'is_dealer')


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
	list_display = ('name', 'status', 'player_count', 'round_mode', 'dealer_restriction', 'created_at')
	list_filter = ('status', 'round_mode', 'dealer_restriction')
	search_fields = ('name', 'players__name')
	readonly_fields = ('created_at',)
	inlines = [PlayerInline]

	@admin.display(description='Players')
	def player_count(self, obj):
		return obj.players.count()


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
	list_display = ('name', 'game', 'seat', 'score', 'tricks_won', 'is_dealer')
	list_filter = ('is_dealer', 'game')
	search_fields = ('name', 'game__name')


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
	list_display = ('game', 'number', 'cards_per_player', 'trump_suit', 'status', 'current_player')
	list_filter = ('status', 'trump_suit')
	search_fields = ('game__name',)


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
	list_display = ('round', 'player', 'rank_label', 'suit_label', 'is_played')
	list_filter = ('suit', 'is_played')
	search_fields = ('player__name', 'round__game__name')

	@admin.display(description='Rank', ordering='rank')
	def rank_label(self, obj):
		return obj.get_rank_display()

	@admin.display(description='Suit', ordering='suit')
	def suit_label(self, obj):
		return obj.get_suit_display()


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
	list_display = ('round', 'player', 'amount', 'submitted_at')
	list_filter = ('round__game',)
	search_fields = ('player__name', 'round__game__name')


@admin.register(Trick)
class TrickAdmin(admin.ModelAdmin):
	list_display = ('round', 'number', 'leader', 'lead_suit', 'winner')
	list_filter = ('lead_suit',)
	search_fields = ('leader__name', 'winner__name', 'round__game__name')


@admin.register(PlayedCard)
class PlayedCardAdmin(admin.ModelAdmin):
	list_display = ('trick', 'player', 'card', 'played_at')
	list_filter = ('card__suit',)
	search_fields = ('player__name', 'card__rank', 'trick__round__game__name')
