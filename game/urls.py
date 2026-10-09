from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('register/', views.register_user, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('rules/', views.rules, name='rules'),
    path('scoreboard/', views.scoreboard, name='scoreboard'),
    path('scoreboard/<int:game_id>/', views.scoreboard, name='game-scoreboard'),
    path('game/<int:game_id>/', views.game_room, name='game-room'),
    path('game/<int:game_id>/start/', views.start_game, name='start-game'),
    path('game/<int:game_id>/finish/', views.finish_game, name='finish-game'),
    path('finish-game/', views.finish_game, name='finish-game-generic'),
    path('game/<int:game_id>/save-rounds/', views.save_rounds, name='save-rounds'),
    path('save-rounds/', views.save_rounds, name='save-rounds-generic'),
    path('games/', views.GameListCreateView.as_view(), name='game-list'),
    path('games/<int:game_id>/', views.GameDetailView.as_view(), name='game-detail'),
    path('games/<int:game_id>/manage/', views.GameCrudView.as_view(), name='game-crud'),
    path('games/<int:game_id>/players/', views.add_player, name='add-player'),
    path('rounds/<int:round_id>/deal/', views.deal, name='deal'),
    path('rounds/<int:round_id>/bid/', views.bid, name='bid'),
    path('rounds/<int:round_id>/play/', views.play, name='play'),
    path('analytics/', views.analytics, name='analytics'),
    path('analytics/<str:username>/', views.analytics, name='user-analytics'),
    path('rewards/', views.rewards_page, name='rewards'),
    path('redeem-points/', views.redeem_points, name='redeem-points'),
]
