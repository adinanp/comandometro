from django.urls import reverse
from django.views.generic.edit import CreateView
from apps.core.forms import DeckForm
from apps.pods.mixins import PodMemberRequiredMixin


class DeckCreateView(PodMemberRequiredMixin, CreateView):
    form_class = DeckForm
    template_name = "core/deck_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["pod"] = self.pod
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        player_id = self.request.GET.get("player")
        if player_id:
            initial["player"] = player_id
        return initial

    def get_success_url(self):
        return reverse(
            "core:deck-detail",
            kwargs={"pod_slug": self.pod.slug, "pk": self.object.pk},
        )
