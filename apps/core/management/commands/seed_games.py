import random
from datetime import datetime, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.cards.models import Card
from apps.core.models import (
    Achievement,
    Deck,
    Game,
    GameParticipant,
    Player,
)
from apps.pods.models import Pod

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
    """
    DEV-ONLY TOOL. Apaga todos os Game, GameParticipant e Achievement e
    regenera partidas aleatórias + a lista fixa de EPIC_ACHIEVEMENTS.
    Destrutivo — nunca deve rodar contra dados reais/compartilhados.
    Recusa execução se settings.DEBUG for False.
    """

    help = "[DEV-ONLY] Gera partidas randômicas e popula os feitos épicos da planilha (destrutivo)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pod",
            type=str,
            required=True,
            help="Slug do Pod a ser populado (precisa já existir)",
        )
        parser.add_argument(
            "--total",
            type=int,
            default=50,
            help="Número de partidas a serem criadas (padrão: 50)",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_games é uma dev-tool e recusa rodar com DEBUG=False. "
                "Este comando apaga Game/GameParticipant/Achievement existentes."
            )

        try:
            pod = Pod.objects.get(slug=options["pod"])
        except Pod.DoesNotExist as exc:
            raise CommandError(
                f"Pod com slug '{options['pod']}' não existe. Crie o pod pela "
                "própria aplicação antes de rodar o seed."
            ) from exc

        total_games = options["total"]

        self.stdout.write(f"Limpando partidas, participantes e achievements de {pod}...")
        Achievement.objects.filter(player__pod=pod).delete()
        GameParticipant.objects.filter(game__pod=pod).delete()
        Game.objects.filter(pod=pod).delete()

        players = list(Player.objects.filter(pod=pod))
        eligible_commanders = list(Card.objects.filter(is_commander_eligible=True))
        # Duplas geradas aqui só usam Partner genérico — é a única mecânica
        # onde "pegar 2 ao acaso do pool" já garante uma combinação legal.
        # Backgrounds ficam de fora do pool de comandante único, porque um
        # Background nunca é válido sozinho.
        partner_pool = [
            c for c in eligible_commanders if c.can_have_partner and not c.partner_with_id
        ]
        single_pool = [c for c in eligible_commanders if not c.is_background]

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
                if len(partner_pool) >= 2 and random.random() > 0.5:
                    commanders = random.sample(partner_pool, 2)
                elif single_pool:
                    commanders = [random.choice(single_pool)]
                else:
                    commanders = []

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
                pod=pod,
                date=game_date,
                win_condition=random.choice(WIN_CONDITIONS),
                notes="Partida gerada via CLI.",
                turn_count=random.randint(4, 14),
            )

            placements = list(range(1, len(valid_participants) + 1))
            random.shuffle(placements)

            for idx, (player, deck) in enumerate(valid_participants):
                placement = placements[idx]
                mvp_card = (
                    random.choice(cards) if cards and random.random() > 0.4 else None
                )
                has_biggest_creature = cards and random.random() > 0.7
                biggest_creature = random.choice(cards) if has_biggest_creature else None
                biggest_creature_power = (
                    random.randint(3, 15) if has_biggest_creature else None
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
                    peak_life_total=random.choice([None, random.randint(20, 120)]),
                    board_wipes_count=random.choice([0, 0, 0, 1, 2]),
                    counterspell_count=random.choice([0, 0, 1, 2]),
                    complaint_count=random.choice([0, 0, 0, 1, 2, 3]),
                    is_self_elimination=random.random() < 0.05,
                    biggest_creature=biggest_creature,
                    biggest_creature_power=biggest_creature_power,
                    starting_seat=idx + 1,
                    felt_salty=(placement != 1 and random.random() < 0.3),
                    fun_rating=random.choice([None, 2, 3, 4, 4, 5]),
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
