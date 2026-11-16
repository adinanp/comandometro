from django.core.management.base import BaseCommand

from apps.cards.use_cases import SyncEdhrecThemesUseCase


class Command(BaseCommand):
    help = (
        "Sincroniza o catálogo de temas do EDHREC (lista, top comandantes e "
        "arte do comandante nº 1). Ferramenta de dev/ops: rodar manualmente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            metavar="SLUG",
            help="Sincroniza os detalhes de um único tema (ex.: voltron); pula os comandantes",
        )
        parser.add_argument(
            "--refresh-commanders",
            action="store_true",
            help="Busca de novo os temas de todos os comandantes, não só os que estão sem dados",
        )

    def handle(self, *args, **options):
        result = SyncEdhrecThemesUseCase().execute(
            only=options["only"], refresh_commanders=options["refresh_commanders"]
        )
        total = 1 if options["only"] else result["themes"]
        self.stdout.write(
            self.style.SUCCESS(f"{result['ok']}/{total} temas sincronizados")
        )
        if not options["only"]:
            self.stdout.write(f"{result['commanders']} comandantes atualizados")
        for slug in result["failed"]:
            self.stderr.write(f"Falhou: {slug}")
