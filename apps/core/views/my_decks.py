from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from apps.core.models import Deck, Player
from apps.pods.mixins import PodMemberRequiredMixin


class MyDecksView(PodMemberRequiredMixin, View):
    """"Meus Decks" — decks do Player do usuário logado neste pod."""

    template_name = "core/my_decks.html"

    def get(self, request, *args, **kwargs):
        player = Player.objects.filter(pod=self.pod, user=request.user).first()
        if player is None:
            return redirect(
                reverse("core:player-create", kwargs={"pod_slug": self.pod.slug})
            )
        decks = Deck.objects.filter(player=player).prefetch_related("commanders")
        return render(
            self.request,
            self.template_name,
            {
                "pod": self.pod,
                "membership": self.membership,
                "player": player,
                "decks": decks,
            },
        )


class DeckDeleteView(PodMemberRequiredMixin, View):
    """Exclui um deck — só o dono do deck (mesmo Player do usuário) pode."""

    def post(self, request, *args, **kwargs):
        deck = get_object_or_404(
            Deck, pk=kwargs["pk"], player__pod=self.pod, player__user=request.user
        )
        deck.delete()
        messages.success(request, "Deck excluído.")
        return redirect("core:my-decks", pod_slug=self.pod.slug)
