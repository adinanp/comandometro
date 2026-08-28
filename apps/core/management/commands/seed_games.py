import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.core.models import (
    Achievement,
    Card,
    Deck,
    Game,
    GameParticipant,
    Player,
)

WIN_CONDITIONS = [
    "combat damage",
    "commander damage",
    "combo",
    "alternative win condition",
    "opponent concede",
]

EPIC_ACHIEVEMENTS = [
    {
        "title": "Maior Torment of Hailfire",
        "target_name": "Alex",
        "detail": "x=25",
        "date": "2022-02-10",
    },
    {
        "title": "Maior Torment of Hailfire",
        "target_name": "Sam",
        "detail": "x=32",
        "date": "2023-02-01",
    },
    {
        "title": "Maior Torment of Hailfire",
        "target_name": "Adinan",
        "detail": "x=34",
        "date": "2023-07-03",
    },
    {
        "title": "Matar com Sign in Blood",
        "target_name": "Adinan",
        "detail": "Matou Diogo",
        "date": None,
    },
    {
        "title": "Matar com Sign in Blood",
        "target_name": "Adinan",
        "detail": "Matou Alex",
        "date": "2022-03-26",
    },
    {
        "title": "Maior Yuriko em um Combate",
        "target_name": "Sam",
        "detail": "21 de dano",
        "date": "2022-03-10",
    },
    {
        "title": "Maior Dano em Spell (Não Infinito)",
        "target_name": "Yuri",
        "detail": "490 de dano (Blasphemous Act + Toralf + Fiery Emancipation)",
        "date": "2022-05-29",
    },
    {
        "title": "Maior Storm Count",
        "target_name": "Toshio",
        "detail": "36",
        "date": "2022-03-22",
    },
    {
        "title": "Maior Taxa de Cast de Comandante",
        "target_name": "Adinan",
        "detail": "5 casts (Tergrid)",
        "date": "2022-03-26",
    },
    {
        "title": "Maior Dano de Combate",
        "target_name": "Yuri",
        "detail": "400 de dano (Brudiclad)",
        "date": "2022-04-20",
    },
]


class Command(BaseCommand):
    help = "Gera partidas randômicas e popula os feitos épicos da planilha."

    def add_arguments(self, parser):
        parser.add_argument(
            "--total",
            type=int,
            default=50,
            help="Número de partidas a serem criadas (padrão: 50)",
        )

    def handle(self, *args, **options):
        total_games = options["total"]

        self.stdout.write("Limpando partidas, participantes e achievements antigos...")
        Achievement.objects.all().delete()
        GameParticipant.objects.all().delete()
        Game.objects.all().delete()

        players = list(Player.objects.all())
        eligible_commanders = list(Card.objects.filter(is_commander_eligible=True))

        if len(players) < 4:
            self.stdout.write(
                self.style.ERROR(
                    "É necessário ter pelo menos 4 jogadores cadastrados no banco."
                )
            )
            return

        players_by_name = {p.name.strip().lower(): p for p in players}

        self.stdout.write("Verificando/Gerando Decks para os jogadores...")
        for player in players:
            player_decks = Deck.objects.filter(player=player, is_active=True)
            if not player_decks.exists():
                num_commanders = 1 if not eligible_commanders else random.choice([1, 2])
                commanders = (
                    random.sample(
                        eligible_commanders,
                        min(num_commanders, len(eligible_commanders)),
                    )
                    if eligible_commanders
                    else []
                )

                deck = Deck.objects.create(player=player, is_active=True)
                if commanders:
                    deck.commanders.set(commanders)
                self.stdout.write(f"Deck automático criado para {player}")

        cards = list(Card.objects.all())
        self.stdout.write(f"Gerando {total_games} partidas randômicas...")

        games_created = 0
        for _ in range(total_games):
            num_participants = random.choice([3, 4])
            pod_players = random.sample(players, num_participants)

            valid_participants = []
            for player in pod_players:
                player_decks = list(Deck.objects.filter(player=player, is_active=True))
                if player_decks:
                    valid_participants.append((player, random.choice(player_decks)))

            if len(valid_participants) < 3:
                continue

            random_days_ago = random.randint(0, 60)
            game_date = timezone.now().date() - timedelta(days=random_days_ago)

            game = Game.objects.create(
                date=game_date,
                win_condition=random.choice(WIN_CONDITIONS),
                notes="Partida gerada via CLI.",
            )

            placements = list(range(1, len(valid_participants) + 1))
            random.shuffle(placements)

            for idx, (player, deck) in enumerate(valid_participants):
                placement = placements[idx]
                mvp_card = (
                    random.choice(cards) if cards and random.random() > 0.4 else None
                )

                GameParticipant.objects.create(
                    game=game,
                    player=player,
                    deck=deck,
                    placement=placement,
                    kill_count=(
                        random.randint(0, 3) if placement == 1 else random.randint(0, 1)
                    ),
                    mvp_card=mvp_card,
                )
            games_created += 1

        self.stdout.write(self.style.SUCCESS(f"{games_created} partidas geradas."))

        self.stdout.write("Populando Achievements da planilha...")
        achievements_created = 0

        for ach in EPIC_ACHIEVEMENTS:
            target_key = ach["target_name"].strip().lower()
            assigned_player = players_by_name.get(target_key, random.choice(players))

            ach_date = (
                datetime.strptime(ach["date"], "%Y-%m-%d").date()
                if ach["date"]
                else timezone.now().date()
            )

            Achievement.objects.create(
                player=assigned_player,
                title=ach["title"],
                detail=ach["detail"],
                date=ach_date,
            )
            achievements_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Sucesso! Processo concluído: {games_created} partidas e {achievements_created} achievements cadastrados."
            )
        )
