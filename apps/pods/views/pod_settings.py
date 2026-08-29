from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from apps.pods.forms import PodForm
from apps.pods.mixins import PodOwnerRequiredMixin
from apps.pods.models import Membership


class PodSettingsView(PodOwnerRequiredMixin, View):
    template_name = "pods/pod_settings.html"

    def get(self, request, pod_slug):
        return self._render(PodForm(instance=self.pod))

    def post(self, request, pod_slug):
        action = request.POST.get("action")
        if action == "rename":
            return self._rename(request)
        if action == "regenerate_invite":
            self.pod.regenerate_invite_token()
            messages.success(request, "Link de convite regenerado.")
            return redirect("pod:pod-settings", pod_slug=self.pod.slug)
        if action == "remove_member":
            return self._remove_member(request)
        if action == "delete_pod":
            self.pod.delete()
            messages.success(request, "Pod apagado.")
            return redirect("pods:pod-list")
        return self._render(PodForm(instance=self.pod))

    def _rename(self, request):
        form = PodForm(request.POST, instance=self.pod)
        if form.is_valid():
            form.save()
            messages.success(request, "Pod renomeado.")
            return redirect("pod:pod-settings", pod_slug=self.pod.slug)
        return self._render(form)

    def _remove_member(self, request):
        member_id = request.POST.get("membership_id")
        membership = get_object_or_404(
            Membership.objects.exclude(role=Membership.Role.OWNER),
            pk=member_id,
            pod=self.pod,
        )
        membership.delete()
        messages.success(request, "Membro removido do pod.")
        return redirect("pod:pod-settings", pod_slug=self.pod.slug)

    def _render(self, form):
        invite_url = self.request.build_absolute_uri(
            reverse("pods:pod-join", kwargs={"token": self.pod.invite_token})
        )
        return render(
            self.request,
            self.template_name,
            {
                "pod": self.pod,
                "membership": self.membership,
                "form": form,
                "invite_url": invite_url,
                "members": self.pod.memberships.select_related("user").order_by(
                    "-role", "created_at"
                ),
            },
        )
