from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.cards.use_cases import EnsureThemeSummaryUseCase
from apps.core.models import ThemeDraw
from apps.pods.mixins import PodMemberRequiredMixin


class ThemeSummaryView(PodMemberRequiredMixin, View):
    """
    Devolve (gerando na primeira vez) o resumo de um tema de um sorteio do
    pod. Chamado por fetch na página do sorteio, para a página não esperar
    a LLM. Só aceita temas que estão no sorteio.
    """

    def get(self, request, *args, **kwargs):
        draw = get_object_or_404(ThemeDraw, pod=self.pod, pk=kwargs["pk"])
        seat = get_object_or_404(
            draw.seats.select_related("theme"), theme_id=kwargs["theme_id"]
        )
        return JsonResponse({"summary": EnsureThemeSummaryUseCase().execute(seat.theme)})
