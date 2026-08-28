import json
import logging
import urllib.request
from django.core.management.base import BaseCommand
from apps.core.models import Card

MTGJSON_ATOMIC_URL = "https://mtgjson.com/api/v5/AtomicCards.json"

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Import de dados de produção: baixa o AtomicCards.json do MTGJSON e
    cria/atualiza registros de Card via bulk_create/bulk_update. Seguro
    para rodar em qualquer ambiente (dev, staging, produção).
    """

    help = "Importa/atualiza a base de cartas do Magic a partir do MTGJSON (AtomicCards.json)"

    def handle(self, *args, **options):
        self.stdout.write("Baixando AtomicCards.json do MTGJSON...")
        logger.info("Iniciando download do AtomicCards.json (%s)", MTGJSON_ATOMIC_URL)

        req = urllib.request.Request(
            MTGJSON_ATOMIC_URL, headers={"User-Agent": "Mozilla/5.0"}
        )

        try:
            with urllib.request.urlopen(req) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            logger.exception("Falha ao baixar/parsear o AtomicCards.json")
            raise

        cards_data = payload.get("data", {})
        self.stdout.write(
            f"Total de nomes únicos de cartas encontrados: {len(cards_data)}"
        )
        logger.info("Total de nomes únicos de cartas encontrados: %d", len(cards_data))

        cards_to_create = []
        cards_to_update = []

        existing_cards = {c.name: c for c in Card.objects.all()}

        for card_name, printings in cards_data.items():
            if not printings:
                continue

            card_info = printings[0]

            types = card_info.get("types", [])
            subtypes = card_info.get("subtypes", [])
            supertypes = card_info.get("supertypes", [])
            text = card_info.get("text", "")
            keywords = card_info.get("keywords", [])

            # Lógica de elegibilidade de Comandante
            is_legendary_creature = "Legendary" in supertypes and "Creature" in types
            is_background = "Background" in subtypes
            has_commander_text = "can be your commander" in text.lower()

            is_commander_eligible = (
                is_legendary_creature or is_background or has_commander_text
            )

            # Lógica de Partner / Choose a Background
            is_partner_eligible = (
                "Partner" in keywords
                or "Partner with" in keywords
                or "Choose a Background" in keywords
                or "Doctor's companion" in keywords
            )

            # Processamento de Identidade de Cor (ex: ['G', 'W'] -> 'GW')
            raw_colors = card_info.get("colorIdentity", [])
            wubrg_order = "WUBRG"
            color_identity = "".join([c for c in wubrg_order if c in raw_colors]) or "C"

            # Tratamento seguro para manaValue (previne overflow com cartas como Gleemax)
            raw_mana_value = card_info.get("manaValue", 0)
            try:
                mana_value = min(int(float(raw_mana_value)), 999)
            except (ValueError, TypeError):
                mana_value = 0

            if card_name in existing_cards:
                obj = existing_cards[card_name]
                obj.color_identity = color_identity
                obj.mana_value = mana_value
                obj.is_commander_eligible = is_commander_eligible
                obj.is_partner_eligible = is_partner_eligible
                cards_to_update.append(obj)
            else:
                cards_to_create.append(
                    Card(
                        name=card_name,
                        color_identity=color_identity,
                        mana_value=mana_value,
                        is_commander_eligible=is_commander_eligible,
                        is_partner_eligible=is_partner_eligible,
                    )
                )

        if cards_to_create:
            self.stdout.write(f"Criando {len(cards_to_create)} novas cartas...")
            Card.objects.bulk_create(cards_to_create, batch_size=2000)
            logger.info("Criadas %d novas cartas", len(cards_to_create))

        if cards_to_update:
            self.stdout.write(
                f"Atualizando {len(cards_to_update)} cartas existentes..."
            )
            Card.objects.bulk_update(
                cards_to_update,
                [
                    "color_identity",
                    "mana_value",
                    "is_commander_eligible",
                    "is_partner_eligible",
                ],
                batch_size=2000,
            )
            logger.info("Atualizadas %d cartas existentes", len(cards_to_update))

        self.stdout.write(self.style.SUCCESS("Base de cartas atualizada com sucesso!"))
        logger.info("Import do MTGJSON concluído com sucesso")
