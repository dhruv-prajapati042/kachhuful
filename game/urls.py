from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('rules/', views.rules, name='rules'),
    path('scoreboard/', views.scoreboard, name='scoreboard'),
    path('scoreboard/<int:game_id>/', views.scoreboard, name='game-scoreboard'),
    path('game/<int:game_id>/', views.game_room, name='game-room'),
    path('game/<int:game_id>/start/', views.start_game, name='start-game'),
    path('games/', views.GameListCreateView.as_view(), name='game-list'),
    path('games/<int:game_id>/', views.GameDetailView.as_view(), name='game-detail'),
    path('games/<int:game_id>/manage/', views.GameCrudView.as_view(), name='game-crud'),
    path('games/<int:game_id>/players/', views.add_player, name='add-player'),
    path('rounds/<int:round_id>/deal/', views.deal, name='deal'),
    path('rounds/<int:round_id>/bid/', views.bid, name='bid'),
    path('rounds/<int:round_id>/play/', views.play, name='play'),
]
