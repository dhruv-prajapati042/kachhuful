from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game, Player, Round
from .serializers import CardActionSerializer, GameSerializer, GameWriteSerializer
from .services import deal_round, play_card, submit_bid


def dashboard(request):
	return render(request, 'game/dashboard.html', {'games': Game.objects.prefetch_related('players').order_by('-created_at')})


def rules(request):
	return render(request, 'game/rules.html')


def scoreboard(request, game_id=None):
	game = Game.objects.prefetch_related('players').filter(id=game_id).first() if game_id else None
	player_names = list(game.players.values_list('name', flat=True)) if game else []
	max_cards = game.rounds.order_by('-number').values_list('cards_per_player', flat=True).first() if game else 52
	return render(request, 'game/scoreboard.html', {'game': game, 'player_names': player_names, 'max_cards': max_cards or 52})


def game_room(request, game_id):
	game = get_object_or_404(Game.objects.prefetch_related('players', 'rounds'), id=game_id)
	round_obj = game.rounds.order_by('-number').first()
	return render(request, 'game/room.html', {'game': game, 'round_obj': round_obj, 'players_needed': max(0, 3 - game.players.count())})


def start_game(request, game_id):
	game = get_object_or_404(Game, id=game_id)
	if request.method != 'POST':
		return JsonResponse({'detail': 'POST required.'}, status=405)
	player_count = game.players.count()
	if player_count < 3:
		messages.error(request, 'At least 3 players are required to start a game.')
		return redirect('game-room', game_id=game.id)
	if player_count > 8:
		messages.error(request, 'A game cannot have more than 8 players.')
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


def add_player(request, game_id):
	game = get_object_or_404(Game, id=game_id)
	if request.method != 'POST':
		return JsonResponse({'detail': 'POST required.'}, status=405)
	if game.players.count() >= 8:
		if request.headers.get('Accept') == 'application/json':
			return JsonResponse({'detail': 'This table already has the maximum of 8 players.'}, status=400)
		messages.error(request, 'This table is full. Kachhu Ful supports a maximum of 8 players.')
		return redirect('game-room', game_id=game.id)
	name = request.POST.get('name', '').strip()
	if not name:
		return JsonResponse({'detail': 'Player name is required.'}, status=400)
	player = Player.objects.create(game=game, name=name, seat=game.players.count() + 1)
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
	return JsonResponse({'bid_id': created.id, 'phase': round_obj.status})


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

# Create your views here.
