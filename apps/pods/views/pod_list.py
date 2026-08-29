from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from apps.pods.models import Pod


class PodListView(LoginRequiredMixin, ListView):
    template_name = "pods/pod_list.html"
    context_object_name = "pods"

    def get_queryset(self):
        return Pod.objects.filter(memberships__user=self.request.user).order_by("name")
