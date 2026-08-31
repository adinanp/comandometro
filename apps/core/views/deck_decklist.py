from django.views.generic import DetailView
from apps.cards.use_cases import EnsureCardImageUseCase
from apps.core.models import Deck
from apps.pods.mixins import PodMemberRequiredMixin


class DeckDecklistView(PodMemberRequiredMixin, DetailView):
    """
    Esqueleto da visão de decklist (inspirada em sites tipo Moxfield) — por
    enquanto só mostra o(s) comandante(s), já que o cadastro da lista
    completa de cartas ainda não existe. Sem filtros/tags/busca, só o
    layout base pra crescer depois.
    """

    model = Deck
    template_name = "core/deck_decklist.html"
    context_object_name = "deck"

    def get_queryset(self):
        return Deck.objects.filter(player__pod=self.pod).select_related("player")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        image_use_case = EnsureCardImageUseCase()
        context["commander_images"] = [
            (card, image_use_case.execute(card))
            for card in self.object.commanders.all()
        ]
        return context
