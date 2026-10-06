# Kachhu Ful

Django + Bootstrap implementation of the Gujarati Kachuful exact-bid trick-taking game.

## Setup on Windows

The project already includes a local `.venv` with Django, Django REST Framework, and Channels installed.

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

For a fresh machine:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
```

## Implemented rules

- 3-8 players per game.
- Configurable up/down round schedule, capped by `floor(52 / player_count)`.
- Trump rotation: Spades, Diamonds, Clubs, Hearts.
- Valid bids are zero through the number of cards in the round.
- Optional “screw the dealer” restriction.
- Server-side phase, turn, ownership, and follow-suit validation.
- Trump beats non-trump cards; otherwise the highest card of the lead suit wins.
- Bootstrap dashboard and game room.

The rule settings are in `config/settings.py` under `GAME_SETTINGS`.
