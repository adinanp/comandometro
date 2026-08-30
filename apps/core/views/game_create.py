from django.shortcuts import redirect, render
from django.views import View
from apps.core.forms import (
    AchievementFormSet,
    DeckForm,
    GameForm,
    GameParticipantFormSet,
    save_achievements,
    save_participants,
)
from apps.pods.mixins import PodMemberRequiredMixin


class GameCreateView(PodMemberRequiredMixin, View):
    template_name = "core/game_form.html"

    def get(self, request, *args, **kwargs):
        game_form = GameForm()
        formset = GameParticipantFormSet(form_kwargs={"pod": self.pod})
        achievement_formset = AchievementFormSet(
            form_kwargs={"pod": self.pod}, prefix="achievements"
        )
        return self._render(game_form, formset, achievement_formset)

    def post(self, request, *args, **kwargs):
        game_form = GameForm(request.POST)
        formset = GameParticipantFormSet(request.POST, form_kwargs={"pod": self.pod})
        achievement_formset = AchievementFormSet(
            request.POST, form_kwargs={"pod": self.pod}, prefix="achievements"
        )
        if game_form.is_valid() and formset.is_valid() and achievement_formset.is_valid():
            game = game_form.save(commit=False)
            game.pod = self.pod
            game.save()
            save_participants(game, formset)
            save_achievements(game, achievement_formset)
            return redirect("core:game-detail", pod_slug=self.pod.slug, pk=game.pk)
        return self._render(game_form, formset, achievement_formset)

    def _render(self, game_form, formset, achievement_formset):
        return render(
            self.request,
            self.template_name,
            {
                "pod": self.pod,
                "membership": self.membership,
                "game_form": game_form,
                "formset": formset,
                "achievement_formset": achievement_formset,
                "deck_modal_form": DeckForm(pod=self.pod, prefix="new_deck"),
                "is_edit": False,
            },
        )
