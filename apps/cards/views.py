from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from .models import Card

MAX_RESULTS = 20


class CardSearchView(LoginRequiredMixin, View):
    """
    Busca de cartas por nome, usada pelos campos de comandante/MVP em vez
    de um <select> gigante. Devolve as flags de habilidade de dupla (Partner
    e variantes) de cada carta, pro front-end decidir se mostra a opção de
    segundo comandante sem precisar de outra requisição.
    """

    def get(self, request):
        query = request.GET.get("q", "").strip()
        if len(query) < 2:
            return JsonResponse({"results": []})

        cards = Card.objects.filter(name__icontains=query)
        if request.GET.get("commander_only"):
            cards = cards.filter(is_commander_eligible=True)
        cards = cards.select_related("partner_with").order_by("name")[:MAX_RESULTS]

        results = [
            {
                "id": card.id,
                "name": card.name,
                "can_have_partner": card.can_have_partner,
                "can_choose_background": card.can_choose_background,
                "is_background": card.is_background,
                "has_doctors_companion": card.has_doctors_companion,
                "is_the_doctor": card.is_the_doctor,
                "partner_with_id": card.partner_with_id,
                "partner_with_name": card.partner_with.name if card.partner_with else None,
            }
            for card in cards
        ]
        return JsonResponse({"results": results})
