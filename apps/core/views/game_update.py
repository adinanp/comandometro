from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from apps.core.forms import (
    AchievementFormSet,
    DeckForm,
    GameForm,
    GameParticipantFormSet,
    save_achievements,
    save_participants,
)
from apps.core.models import Game
from apps.pods.mixins import PodMemberRequiredMixin


class GameUpdateView(PodMemberRequiredMixin, View):
    """
    Edita uma partida já registrada — dados da partida, participantes já
    existentes (pra corrigir coisas como esquecer de marcar o vencedor) e
    achievements (pra acrescentar um feito lembrado depois).
    """

    template_name = "core/game_form.html"

    def _get_game(self):
        return get_object_or_404(Game, pk=self.kwargs["pk"], pod=self.pod)

    def get(self, request, *args, **kwargs):
        game = self._get_game()
        game_form = GameForm(instance=game)
        formset = GameParticipantFormSet(
            initial=self._participants_initial(game), form_kwargs={"pod": self.pod}
        )
        achievement_formset = AchievementFormSet(
            initial=self._achievements_initial(game),
            form_kwargs={"pod": self.pod},
            prefix="achievements",
        )
        return self._render(game, game_form, formset, achievement_formset)

    def post(self, request, *args, **kwargs):
        game = self._get_game()
        game_form = GameForm(request.POST, instance=game)
        formset = GameParticipantFormSet(
            request.POST,
            initial=self._participants_initial(game),
            form_kwargs={"pod": self.pod},
        )
        achievement_formset = AchievementFormSet(
            request.POST,
            initial=self._achievements_initial(game),
            form_kwargs={"pod": self.pod},
            prefix="achievements",
        )
        if game_form.is_valid() and formset.is_valid() and achievement_formset.is_valid():
            game = game_form.save(commit=False)
            game.pod = self.pod
            game.save()
            save_participants(game, formset)
            save_achievements(game, achievement_formset)
            return redirect("core:game-detail", pod_slug=self.pod.slug, pk=game.pk)
        return self._render(game, game_form, formset, achievement_formset)

    def _participants_initial(self, game):
        return [
            {
                "existing_id": p.pk,
                "player": p.player_id,
                "deck": p.deck_id,
                "placement": p.placement,
                "kill_count": p.kill_count,
                "mvp_card": p.mvp_card_id,
                "peak_life_total": p.peak_life_total,
                "board_wipes_count": p.board_wipes_count,
                "counterspell_count": p.counterspell_count,
                "complaint_count": p.complaint_count,
                "is_self_elimination": p.is_self_elimination,
                "starting_seat": p.starting_seat,
                "felt_salty": p.felt_salty,
            }
            for p in game.participants.all()
        ]

    def _achievements_initial(self, game):
        return [
            {
                "existing_id": a.pk,
                "player": a.player_id,
                "title": a.title,
                "detail": a.detail,
            }
            for a in game.achievements.all()
        ]

    def _render(self, game, game_form, formset, achievement_formset):
        return render(
            self.request,
            self.template_name,
            {
                "pod": self.pod,
                "membership": self.membership,
                "game": game,
                "game_form": game_form,
                "formset": formset,
                "achievement_formset": achievement_formset,
                "deck_modal_form": DeckForm(pod=self.pod, prefix="new_deck"),
                "is_edit": True,
            },
        )
