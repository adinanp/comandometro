from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic.edit import FormView
from apps.pods.forms import PodForm
from apps.pods.use_cases import CreatePodUseCase


class PodCreateView(LoginRequiredMixin, FormView):
    form_class = PodForm
    template_name = "pods/pod_form.html"

    def form_valid(self, form):
        self.pod = CreatePodUseCase().execute(
            user=self.request.user, name=form.cleaned_data["name"]
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("core:dashboard", kwargs={"pod_slug": self.pod.slug})
