import json
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game, Player, Round, Bid, Trick
from .serializers import CardActionSerializer, GameSerializer, GameWriteSerializer
from .services import deal_round, get_round_trick_stats, play_card, submit_bid, send_game_finished_emails


def dashboard(request):
	return render(request, 'game/dashboard.html', {'games': Game.objects.prefetch_related('players').order_by('-created_at')})


def rules(request):
	return render(request, 'game/rules.html')


def scoreboard(request, game_id=None):
	game = Game.objects.prefetch_related('players', 'rounds').filter(id=game_id).first() if game_id else None
	player_names = list(game.players.values_list('name', flat=True)) if game else []
	player_count = len(player_names) or 5
	deck_count = game.deck_count if game else 1
	max_cards = max(1, (52 * deck_count) // player_count)
	is_finished = (game.status == Game.Status.FINISHED) if game else False
	registered_users = list(User.objects.values('id', 'username', 'first_name', 'email'))
	return render(request, 'game/scoreboard.html', {
		'game': game,
		'player_names': player_names,
		'player_count': player_count,
		'deck_count': deck_count,
		'max_cards': max_cards,
		'is_finished': is_finished,
		'registered_users': registered_users,
	})


def finish_game(request, game_id=None):
	if request.method != 'POST':
		return JsonResponse({'detail': 'POST required.'}, status=405)
	game = get_object_or_404(Game, id=game_id) if game_id else None
	game_name = game.name if game else 'Kachhu Ful Game'
	if game:
		game.status = Game.Status.FINISHED
		game.save(update_fields=['status'])

	player_list = []
	if request.content_type == 'application/json':
		try:
			data = json.loads(request.body)
			player_list = data.get('players', [])
		except Exception:
			player_list = []

	if not player_list and game:
		player_list = [{'name': p.name, 'email': p.email, 'score': p.score} for p in game.players.all()]

	if game and player_list:
		for pdata in player_list:
			p_name = pdata.get('name')
			p_score = pdata.get('score', 0)
			if p_name:
				p_obj = game.players.filter(name__iexact=p_name).first()
				if p_obj:
					p_obj.score = int(p_score)
					if pdata.get('email'):
						p_obj.email = pdata.get('email')
					p_obj.save()

	email_results = send_game_finished_emails(game_name, player_list)

	if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
		return JsonResponse({
			'status': 'success',
			'game_name': game_name,
			'email_results': email_results,
			'message': f"Game finished! Emails dispatched ({email_results.get('winners_sent', 0)} winners, {email_results.get('losers_sent', 0)} losers)."
		})

	messages.success(request, f'Game "{game_name}" is now finished! Revealing final scorecard & emails sent.')
	return redirect(f'/scoreboard/{game.id}/?finished=1' if game else '/scoreboard/?finished=1')


def game_room(request, game_id):
	game = get_object_or_404(Game.objects.prefetch_related('players', 'rounds'), id=game_id)
	round_obj = game.rounds.order_by('-number').first()
	p_count = max(2, game.players.count())
	trick_stats = get_round_trick_stats(p_count, round_obj.number, game.round_mode, game.deck_count) if round_obj else None
	registered_users = User.objects.all().order_by('first_name', 'username')
	return render(request, 'game/room.html', {
		'game': game,
		'round_obj': round_obj,
		'trick_stats': trick_stats,
		'players_needed': max(0, 3 - game.players.count()),
		'registered_users': registered_users,
	})



def start_game(request, game_id):
	game = get_object_or_404(Game, id=game_id)
	if request.method != 'POST':
		return JsonResponse({'detail': 'POST required.'}, status=405)
	player_count = game.players.count()
	if player_count < 2:
		messages.error(request, 'At least 2 players are required to start a game.')
		return redirect('game-room', game_id=game.id)
	if not game.rounds.exists():
		deal_round(game, 1)
	game.status = Game.Status.BIDDING
	game.current_round = 1
	game.save(update_fields=['status', 'current_round'])
	return redirect('game-scoreboard', game_id=game.id)


class GameListCreateView(generics.ListCreateAPIView):
	queryset = Game.objects.all()
	serializer_class = GameSerializer


class GameDetailView(generics.RetrieveAPIView):
	queryset = Game.objects.prefetch_related('players', 'rounds')
	serializer_class = GameSerializer
	lookup_url_kwarg = 'game_id'


class GameCrudView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Game.objects.all()
	serializer_class = GameWriteSerializer
	lookup_url_kwarg = 'game_id'


def register_user(request):
	if request.method == 'POST':
		name = request.POST.get('name', '').strip()
		email = request.POST.get('email', '').strip()
		password = request.POST.get('password', '')
		if not name or not email or not password:
			messages.error(request, 'Name, Email, and Password are all required.')
			return render(request, 'registration/register.html')
		if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
			messages.error(request, 'An account with this email already exists.')
			return render(request, 'registration/register.html')
		user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
		login(request, user)
		messages.success(request, f'Welcome, {name}! Registration successful.')
		next_url = request.GET.get('next') or 'dashboard'
		return redirect(next_url)
	return render(request, 'registration/register.html')


def login_user(request):
	if request.method == 'POST':
		email = request.POST.get('email', '').strip()
		password = request.POST.get('password', '')
		user_obj = User.objects.filter(email=email).first() or User.objects.filter(username=email).first()
		username = user_obj.username if user_obj else email
		user = authenticate(request, username=username, password=password)
		if user is not None:
			login(request, user)
			messages.success(request, f'Welcome back, {user.first_name or user.username}!')
			next_url = request.GET.get('next') or 'dashboard'
			return redirect(next_url)
		messages.error(request, 'Invalid email or password.')
	return render(request, 'registration/login.html')


def logout_user(request):
	logout(request)
	messages.success(request, 'You have been logged out.')
	return redirect('dashboard')


def add_player(request, game_id):
	game = get_object_or_404(Game, id=game_id)
	if request.method != 'POST':
		return JsonResponse({'detail': 'POST required.'}, status=405)
	name = request.POST.get('name', '').strip()
	email = request.POST.get('email', '').strip()
	if not name:
		return JsonResponse({'detail': 'Player name is required.'}, status=400)
	player = Player.objects.create(game=game, name=name, email=email, seat=game.players.count() + 1)
	messages.success(request, f'Player "{name}" successfully joined!')
	return redirect('game-room', game_id=game.id)



def deal(request, round_id):
	round_obj = get_object_or_404(Round, id=round_id)
	try:
		next_round = deal_round(round_obj.game, round_obj.number + 1)
	except ValidationError as error:
		return JsonResponse({'detail': error.messages}, status=400)
	return JsonResponse({'round_id': next_round.id, 'trump_suit': next_round.trump_suit, 'cards_per_player': next_round.cards_per_player})


def bid(request, round_id):
	round_obj = get_object_or_404(Round.objects.select_related('game'), id=round_id)
	try:
		player = round_obj.game.players.get(id=request.POST.get('player_id'))
		created = submit_bid(round_obj, player, int(request.POST.get('amount')))
	except (Player.DoesNotExist, TypeError, ValueError, ValidationError) as error:
		return JsonResponse({'detail': str(error)}, status=400)
def play(request, round_id):
	round_obj = get_object_or_404(Round.objects.select_related('game'), id=round_id)
	payload = CardActionSerializer(data=request.POST)
	if not payload.is_valid():
		return Response(payload.errors, status=status.HTTP_400_BAD_REQUEST)
	try:
		player = round_obj.game.players.get(id=payload.validated_data['player_id'])
		card = play_card(round_obj, player, payload.validated_data['card_id'])
	except (Player.DoesNotExist, ValidationError) as error:
		return JsonResponse({'detail': str(error)}, status=400)
	return JsonResponse({'card_id': card.id, 'phase': round_obj.status, 'current_player': round_obj.current_player_id})


def analytics(request, username=None):
	registered_users = list(User.objects.values('id', 'username', 'first_name', 'email'))
	search_query = request.GET.get('query', '').strip()
	
	target_name = username or search_query
	if not target_name and request.user.is_authenticated:
		target_name = request.user.first_name or request.user.username
	if not target_name and registered_users:
		target_name = registered_users[0]['first_name'] or registered_users[0]['username']
	if not target_name:
		target_name = 'Player 1'

	player_records = Player.objects.filter(name__iexact=target_name).select_related('game')
	total_games = player_records.count()
	
	total_points = 0
	games_won = 0
	total_bids = 0
	exact_hits = 0
	highest_score = 0
	match_history = []

	for p in player_records:
		game = p.game
		game_players = list(game.players.all())
		if not game_players:
			continue

		scores = [gp.score for gp in game_players]
		max_score = max(scores) if scores else 0
		
		is_winner = (p.score == max_score and p.score > 0)
		if is_winner:
			games_won += 1
			
		if p.score > highest_score:
			highest_score = p.score
			
		total_points += p.score

		p_bids = Bid.objects.filter(player=p).select_related('round')
		game_exact_hits = 0
		game_total_bids = p_bids.count()
		for b in p_bids:
			tricks_won = Trick.objects.filter(round=b.round, winner=p).count()
			if b.amount == tricks_won:
				game_exact_hits += 1

		total_bids += game_total_bids
		exact_hits += game_exact_hits
		
		sorted_players = sorted(game_players, key=lambda gp: gp.score, reverse=True)
		rank = next((idx + 1 for idx, gp in enumerate(sorted_players) if gp.id == p.id), len(sorted_players))
		accuracy = round((game_exact_hits / game_total_bids * 100), 1) if game_total_bids > 0 else 0

		match_history.append({
			'game_id': game.id,
			'game_name': game.name,
			'created_at': game.created_at,
			'score': p.score,
			'rank': rank,
			'total_players': len(game_players),
			'exact_hits': game_exact_hits,
			'total_bids': game_total_bids,
			'accuracy': accuracy,
			'status': game.status,
			'is_winner': is_winner,
		})

	match_history.sort(key=lambda x: x['created_at'], reverse=True)

	win_rate = round((games_won / total_games * 100), 1) if total_games > 0 else 0
	bid_accuracy = round((exact_hits / total_bids * 100), 1) if total_bids > 0 else 0
	avg_score = round(total_points / total_games, 1) if total_games > 0 else 0

	return render(request, 'game/analytics.html', {
		'target_name': target_name,
		'registered_users': registered_users,
		'total_games': total_games,
		'games_won': games_won,
		'win_rate': win_rate,
		'total_points': total_points,
		'avg_score': avg_score,
		'highest_score': highest_score,
		'total_bids': total_bids,
		'exact_hits': exact_hits,
		'bid_accuracy': bid_accuracy,
		'match_history': match_history,
	})


import random
import string
from django.contrib.auth.decorators import login_required
from .models import UserReward


def rewards_page(request):
	reward = None
	if request.user.is_authenticated:
		reward, _ = UserReward.objects.get_or_create(user=request.user)
	
	streak_days_list = [
		{'day': 1, 'pts': 1},
		{'day': 2, 'pts': 2},
		{'day': 3, 'pts': 3},
		{'day': 4, 'pts': 4},
		{'day': 5, 'pts': 5},
		{'day': 6, 'pts': 6},
		{'day': 7, 'pts': 7},
	]
	return render(request, 'game/rewards.html', {
		'reward': reward,
		'streak_days_list': streak_days_list,
	})


@login_required
def redeem_points(request):
	if request.method != 'POST':
		return JsonResponse({'detail': 'POST required.'}, status=405)
	
	reward, _ = UserReward.objects.get_or_create(user=request.user)
	if reward.points < 100:
		return JsonResponse({
			'status': 'error',
			'message': f"Insufficient points! You need at least 100 points to redeem. (Current balance: {reward.points} Points)"
		}, status=400)

	reward.points -= 100
	reward.total_points_redeemed += 100
	reward.save()

	code_digits = ''.join(random.choices(string.digits, k=6))
	voucher_code = f"KF-REDEEM-{code_digits}"

	return JsonResponse({
		'status': 'success',
		'voucher_code': voucher_code,
		'remaining_points': reward.points,
		'message': f"🎉 Successfully redeemed 100 points! Your Reward Voucher Code: {voucher_code}"
	})
