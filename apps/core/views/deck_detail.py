from django.views.generic import DetailView
from apps.core.models import Deck
from apps.core.use_cases import DeckDetailUseCase, EnsureCardImageUseCase


class DeckDetailView(DetailView):
    model = Deck
    template_name = "core/deck_detail.html"
    context_object_name = "deck"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DeckDetailUseCase().execute(self.object))

        image_use_case = EnsureCardImageUseCase()
        context["commander_images"] = [
            (card, image_use_case.execute(card))
            for card in self.object.commanders.all()
        ]
        return context
