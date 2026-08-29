from django.urls import reverse
from django.views.generic.edit import CreateView
from apps.core.forms import PlayerForm
from apps.pods.mixins import PodMemberRequiredMixin


class PlayerCreateView(PodMemberRequiredMixin, CreateView):
    form_class = PlayerForm
    template_name = "core/player_form.html"

    def form_valid(self, form):
        form.instance.pod = self.pod
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "core:player-profile",
            kwargs={"pod_slug": self.pod.slug, "pk": self.object.pk},
        )
