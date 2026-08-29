from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from apps.pods.models import Membership, Pod
from apps.pods.use_cases import JoinPodUseCase


class PodJoinView(LoginRequiredMixin, View):
    template_name = "pods/pod_join.html"

    def _get_pod(self, token):
        return get_object_or_404(Pod, invite_token=token)

    def get(self, request, token):
        pod = self._get_pod(token)
        if Membership.objects.filter(pod=pod, user=request.user).exists():
            return redirect("core:dashboard", pod_slug=pod.slug)
        return render(request, self.template_name, {"invited_pod": pod, "token": token})

    def post(self, request, token):
        pod = self._get_pod(token)
        try:
            pod = JoinPodUseCase().execute(user=request.user, invite_token=token)
        except Pod.DoesNotExist as exc:
            raise Http404 from exc
        return redirect("core:dashboard", pod_slug=pod.slug)
