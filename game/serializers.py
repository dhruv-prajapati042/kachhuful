from rest_framework import serializers

from .models import Bid, Card, Game, Player, Round


class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['id', 'name', 'email', 'seat', 'score', 'tricks_won', 'is_dealer']


class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = ['id', 'suit', 'rank', 'is_played']


class RoundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Round
        fields = ['id', 'number', 'cards_per_player', 'trump_suit', 'status', 'leader', 'current_player']


class GameSerializer(serializers.ModelSerializer):
    players = PlayerSerializer(many=True, read_only=True)
    rounds = RoundSerializer(many=True, read_only=True)

    class Meta:
        model = Game
        fields = ['id', 'name', 'status', 'dealer_restriction', 'round_mode', 'deck_count', 'current_round', 'players', 'rounds']


class GameWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ['id', 'name', 'status', 'dealer_restriction', 'round_mode', 'deck_count', 'current_round']


class BidSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bid
        fields = ['id', 'round', 'player', 'amount']


class CardActionSerializer(serializers.Serializer):
    player_id = serializers.IntegerField()
    card_id = serializers.IntegerField()
