import json
import logging
import urllib.request
from django.core.management.base import BaseCommand
from apps.cards.models import Card

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
        partner_with_names = {}

        existing_cards = {c.name: c for c in Card.objects.all()}

        for card_name, printings in cards_data.items():
            if not printings:
                continue

            card_info = printings[0]

            subtypes = card_info.get("subtypes") or []
            supertypes = card_info.get("supertypes", [])
            text = card_info.get("text") or ""
            keywords = card_info.get("keywords") or []

            # Lógica de elegibilidade de Comandante
            is_legendary = "Legendary" in supertypes
            # Regra atualizada: além de criaturas lendárias, qualquer permanente
            # lendário com poder e resistência impressos pode ser comandante —
            # cobre veículos e spacecraft lendários (que não são criaturas por
            # padrão), sem precisar checar o tipo "Creature" separadamente.
            has_power_and_toughness = (
                card_info.get("power") is not None
                and card_info.get("toughness") is not None
            )
            is_legendary_pt_permanent = is_legendary and has_power_and_toughness
            is_background_card = "Background" in subtypes
            has_commander_text = "can be your commander" in text.lower()

            is_commander_eligible = (
                is_legendary_pt_permanent or is_background_card or has_commander_text
            )

            # Habilidades de dupla de comandante. O MTGJSON grava o keyword de
            # "Choose a Background" com "b" minúsculo — case importa aqui.
            can_have_partner = "Partner" in keywords
            can_choose_background = "Choose a background" in keywords
            has_doctors_companion = "Doctor's companion" in keywords
            # "The Doctor" (Doctor Who) não dá pra identificar só pelo subtipo
            # "Doctor" (várias cartas sem relação nenhuma usam esse subtipo,
            # ex: Doc Samson) — o marcador real é "Time Lord" + "Doctor" juntos.
            is_the_doctor_card = "Time Lord" in subtypes and "Doctor" in subtypes

            # "Partner with X" é nomeado — o nome do parceiro só existe no
            # texto da carta ("Partner with <Nome> (...)"), guardamos numa
            # segunda passada depois que todas as cartas tiverem PK.
            partner_with_name = None
            if "Partner with" in keywords:
                for line in text.splitlines():
                    if line.startswith("Partner with "):
                        partner_with_name = (
                            line[len("Partner with ") :].split(" (", 1)[0].strip()
                        )
                        break
            if partner_with_name:
                partner_with_names[card_name] = partner_with_name

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

            # AtomicCards só traz o Oracle ID (compartilhado entre reimpressões),
            # não o scryfallId de uma printing específica.
            identifiers = card_info.get("identifiers", {})
            scryfall_oracle_id = identifiers.get("scryfallOracleId", "")

            field_values = {
                "color_identity": color_identity,
                "mana_value": mana_value,
                "is_commander_eligible": is_commander_eligible,
                "can_have_partner": can_have_partner,
                "can_choose_background": can_choose_background,
                "is_background": is_background_card,
                "has_doctors_companion": has_doctors_companion,
                "is_the_doctor": is_the_doctor_card,
                "scryfall_oracle_id": scryfall_oracle_id,
            }

            if card_name in existing_cards:
                obj = existing_cards[card_name]
                for field, value in field_values.items():
                    setattr(obj, field, value)
                cards_to_update.append(obj)
            else:
                cards_to_create.append(Card(name=card_name, **field_values))

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
                    "can_have_partner",
                    "can_choose_background",
                    "is_background",
                    "has_doctors_companion",
                    "is_the_doctor",
                    "scryfall_oracle_id",
                ],
                batch_size=2000,
            )
            logger.info("Atualizadas %d cartas existentes", len(cards_to_update))

        if partner_with_names:
            self.stdout.write(
                f"Resolvendo {len(partner_with_names)} parceiros nomeados (Partner with)..."
            )
            all_cards_by_name = {c.name: c for c in Card.objects.all()}
            cards_to_link = []
            unresolved = []
            for card_name, partner_name in partner_with_names.items():
                card = all_cards_by_name.get(card_name)
                partner = all_cards_by_name.get(partner_name)
                if not card:
                    continue
                if partner:
                    card.partner_with = partner
                    cards_to_link.append(card)
                else:
                    unresolved.append((card_name, partner_name))
            if cards_to_link:
                Card.objects.bulk_update(
                    cards_to_link, ["partner_with"], batch_size=2000
                )
                logger.info("Vinculados %d parceiros nomeados", len(cards_to_link))
            if unresolved:
                logger.warning(
                    "Não foi possível resolver %d parceiros nomeados: %s",
                    len(unresolved),
                    unresolved[:10],
                )

        self.stdout.write(self.style.SUCCESS("Base de cartas atualizada com sucesso!"))
        logger.info("Import do MTGJSON concluído com sucesso")
