from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from .models import Bid, Card, Game, PlayedCard, Player, RewardRedemption, Round, Trick, UserReward


def bulk_add_users_view(request):
	if request.method == 'POST':
		default_password = request.POST.get('default_password', 'Kachuful@123').strip() or 'Kachuful@123'
		user_data = request.POST.get('user_data', '').strip()
		lines = [line.strip() for line in user_data.splitlines() if line.strip()]
		created_count = 0
		skipped_count = 0

		for line in lines:
			parts = [p.strip() for p in line.split(',')]
			name = parts[0] if len(parts) > 0 else ''
			email = parts[1] if len(parts) > 1 else parts[0]

			if not email or '@' not in email:
				username = name.lower().replace(' ', '_')
				email = f"{username}@example.com"
			else:
				username = email

			if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
				skipped_count += 1
				continue

			user = User.objects.create_user(
				username=username,
				email=email,
				password=default_password,
				first_name=name,
				is_staff=False,       # Regular non-admin role!
				is_superuser=False    # Regular non-admin role!
			)
			UserReward.objects.get_or_create(user=user)
			created_count += 1

		messages.success(request, f'Successfully created {created_count} regular non-admin user(s)! ({skipped_count} skipped/already exist). Default Password: {default_password}')
		return redirect('/admin/auth/user/')

	context = admin.site.each_context(request)
	context['title'] = 'Bulk Add Regular Users (Non-Admin)'
	return TemplateResponse(request, 'admin/bulk_add_users.html', context)


class UserRewardInline(admin.StackedInline):
	model = UserReward
	can_delete = False
	verbose_name_plural = 'Kachhuful Points & Daily Streak'


class CustomUserAdmin(UserAdmin):
	change_list_template = "admin/user_change_list.html"
	inlines = [UserRewardInline]
	list_display = ('username', 'first_name', 'email', 'kachhuful_points', 'is_staff')

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path('bulk-add/', self.admin_site.admin_view(bulk_add_users_view), name='bulk-add-users'),
		]
		return custom_urls + urls

	@admin.display(description='🪙 Points')
	def kachhuful_points(self, obj):
		reward = getattr(obj, 'reward', None)
		return f"🪙 {reward.points} Points" if reward else "🪙 0 Points"


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(UserReward)
class UserRewardAdmin(admin.ModelAdmin):
	list_display = ('user', 'player_name', 'points_badge', 'streak_days', 'last_login_date', 'total_points_earned', 'total_points_redeemed')
	search_fields = ('user__username', 'user__first_name', 'user__email')
	list_filter = ('streak_days', 'last_login_date')

	@admin.display(description='Player Name')
	def player_name(self, obj):
		return obj.user.first_name or obj.user.username

	@admin.display(description='Kachhuful Points')
	def points_badge(self, obj):
		return f"🪙 {obj.points} Points"


@admin.register(RewardRedemption)
class RewardRedemptionAdmin(admin.ModelAdmin):
	list_display = ('user', 'voucher_code', 'points_spent', 'created_at')
	search_fields = ('user__username', 'user__first_name', 'user__email', 'voucher_code')
	list_filter = ('created_at',)


class PlayerInline(admin.TabularInline):
	model = Player
	extra = 5  # Allows adding 5 players at once directly on Game creation page
	fields = ('name', 'email', 'seat', 'score', 'tricks_won', 'is_dealer')


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
	list_display = ('name', 'status', 'player_count', 'round_mode', 'deck_count', 'dealer_restriction', 'created_at')
	list_filter = ('status', 'round_mode', 'dealer_restriction')
	search_fields = ('name', 'players__name', 'players__email')
	readonly_fields = ('created_at',)
	inlines = [PlayerInline]

	@admin.display(description='Players')
	def player_count(self, obj):
		return obj.players.count()


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
	list_display = ('name', 'email', 'game', 'seat', 'score', 'tricks_won', 'is_dealer')
	list_filter = ('is_dealer', 'game')
	search_fields = ('name', 'email', 'game__name')


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
