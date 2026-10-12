# Comandometro

A stats tracker for Magic: The Gathering Commander (EDH) playgroups. Log your pod's games, decks and memorable plays, and see who is winning, with which commanders and how.

> The interface is in Brazilian Portuguese.

## Features

- **Pods (playgroups)**: each pod is isolated, with its own players, decks and games. A user can join several pods through an invite link, and pod owners manage members and settings.
- **Games**: record who played, with which deck, the placement, the win condition, the turn count and details like the biggest creature on the table or who felt salty.
- **Decks**: commanders picked from a full Magic card catalog, with color identity calculated automatically. A deck can have up to two commanders (partners).
- **Players**: players can be linked to an account or added as guests without one, side by side in the same roster.
- **Achievements**: a wall of memorable plays, like the biggest X spell or the most damage in one turn.
- **Dashboard and metrics**: win rates by player, commander and color combination, top 5 rankings and per-player profiles.

## Stack

- Python 3.12 and Django 6
- PostgreSQL
- django-allauth for accounts (username/password and Google)
- Server-rendered templates with Tailwind CSS
- Card catalog imported from [MTGJSON](https://mtgjson.com), card images from [Scryfall](https://scryfall.com)

## Running locally

Requirements: Python 3.12 and Docker.

```bash
docker compose up -d                 # PostgreSQL on port 5432
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/local.txt
cp .env.example .env                 # set SECRET_KEY and DATABASE_URL
python manage.py migrate
python manage.py import_mtgjson      # card catalog, takes a few minutes
python manage.py runserver
```

By default, `manage.py` loads the development settings (`config.settings` imports `config.settings.local`).

To fill a pod with sample data, create the pod in the app first and then run:

```bash
python manage.py seed_games --pod <pod-slug>
```

The seed is destructive and meant for development only.

## Tests

```bash
python manage.py test
```

## Project docs

The [`.docs/`](.docs/README.md) folder (in Portuguese) describes the architecture, the conventions and the practices the project follows.

## Roadmap

- A browser extension that captures games played on [EDHPlay](https://edhplay.com) and an import API to log them automatically ([design spec](docs/superpowers/specs/2026-09-08-edhplay-match-capture-design.md)).
