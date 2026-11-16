from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.cards.use_cases import EnsureThemeSummaryUseCase
from apps.core.models import Player, PlayerWeeklyTheme
from apps.core.use_cases import RerollWeeklyThemeUseCase
from apps.core.use_cases.draw_themes import week_start
from apps.pods.mixins import PodMemberRequiredMixin

ALLOWED_DAYS = {"7", "30"}


class _CurrentPlayerMixin(PodMemberRequiredMixin):
    def current_player(self):
        player = Player.objects.filter(pod=self.pod, user=self.request.user).first()
        if player is None:
            raise Http404("Jogador não encontrado neste pod.")
        return player


class RerollWeeklyThemeView(_CurrentPlayerMixin, View):
    """Botão ⟳ do card: troca o Tema da Semana e volta para o dashboard."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            result = RerollWeeklyThemeUseCase().execute(self.current_player())
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            if result is None:
                messages.error(request, "Não há outro tema disponível para trocar agora.")

        url = reverse("core:dashboard", kwargs={"pod_slug": self.pod.slug})
        days = request.POST.get("days")
        return redirect(f"{url}?days={days}" if days in ALLOWED_DAYS else url)


class WeeklyThemeSummaryView(_CurrentPlayerMixin, View):
    """Resumo (gerado na primeira vez) do Tema da Semana atual do jogador logado."""

    def get(self, request, *args, **kwargs):
        current = (
            PlayerWeeklyTheme.objects.filter(
                player=self.current_player(),
                week_start=week_start(timezone.now()).date(),
            )
            .select_related("theme")
            .first()
        )
        if current is None:
            raise Http404("Sem tema nesta semana.")
        return JsonResponse({"summary": EnsureThemeSummaryUseCase().execute(current.theme)})
