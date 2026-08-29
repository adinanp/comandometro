from django.shortcuts import redirect, render
from django.views import View
from apps.core.forms import DeckForm, GameForm, GameParticipantFormSet, build_participants
from apps.pods.mixins import PodMemberRequiredMixin


class GameCreateView(PodMemberRequiredMixin, View):
    template_name = "core/game_form.html"

    def get(self, request, *args, **kwargs):
        game_form = GameForm()
        formset = GameParticipantFormSet(form_kwargs={"pod": self.pod})
        return self._render(game_form, formset)

    def post(self, request, *args, **kwargs):
        game_form = GameForm(request.POST)
        formset = GameParticipantFormSet(request.POST, form_kwargs={"pod": self.pod})
        if game_form.is_valid() and formset.is_valid():
            game = game_form.save(commit=False)
            game.pod = self.pod
            game.save()
            build_participants(game, formset)
            return redirect("core:game-detail", pod_slug=self.pod.slug, pk=game.pk)
        return self._render(game_form, formset)

    def _render(self, game_form, formset):
        return render(
            self.request,
            self.template_name,
            {
                "pod": self.pod,
                "membership": self.membership,
                "game_form": game_form,
                "formset": formset,
                "deck_modal_form": DeckForm(pod=self.pod, prefix="new_deck"),
            },
        )
