from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views.generic import FormView

from apps.core.forms import ThemeDrawForm
from apps.core.models import Player
from apps.core.use_cases import DrawThemesUseCase
from apps.core.use_cases.draw_themes import PLAYERS_PER_DRAW
from apps.pods.mixins import PodMemberRequiredMixin


class ThemeDrawCreateView(PodMemberRequiredMixin, FormView):
    template_name = "core/theme_draw_form.html"
    form_class = ThemeDrawForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["pod"] = self.pod
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["players_per_draw"] = PLAYERS_PER_DRAW
        context["enough_players"] = (
            Player.objects.filter(pod=self.pod).count() >= PLAYERS_PER_DRAW
        )
        return context

    def form_valid(self, form):
        try:
            draw = DrawThemesUseCase().execute(
                self.pod, list(form.cleaned_data["players"]), created_by=self.request.user
            )
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
            return self.form_invalid(form)
        return redirect("core:theme-draw-detail", pod_slug=self.pod.slug, pk=draw.pk)
