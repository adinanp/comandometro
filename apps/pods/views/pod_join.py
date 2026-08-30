from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from apps.pods.models import Membership, Pod
from apps.pods.use_cases import JoinPodUseCase


class PodJoinView(LoginRequiredMixin, View):
    """
    Resgata o convite e já entra no pod, sem tela de confirmação — clicar
    no link (e estar logado) já é a confirmação, do mesmo jeito que um
    convite do Discord funciona. Se já for membro, só manda pro dashboard.
    """

    def get(self, request, token):
        pod = get_object_or_404(Pod, invite_token=token)
        if not Membership.objects.filter(pod=pod, user=request.user).exists():
            pod = JoinPodUseCase().execute(user=request.user, invite_token=token)
            messages.success(request, f'Você entrou no pod "{pod.name}".')
        return redirect("core:dashboard", pod_slug=pod.slug)
