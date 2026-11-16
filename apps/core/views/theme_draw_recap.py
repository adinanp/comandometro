from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.models import ThemeDraw
from apps.core.use_cases import ThemeDrawRecapUseCase
from apps.pods.mixins import PodMemberRequiredMixin


class ThemeDrawRecapView(PodMemberRequiredMixin, View):
    """Imagem PNG do sorteio para compartilhar no grupo (renderizada a cada pedido)."""

    def get(self, request, *args, **kwargs):
        draw = get_object_or_404(ThemeDraw, pod=self.pod, pk=kwargs["pk"])
        response = HttpResponse(
            ThemeDrawRecapUseCase().execute(draw), content_type="image/png"
        )
        response["Content-Disposition"] = f'inline; filename="sorteio-de-temas-{draw.pk}.png"'
        return response
