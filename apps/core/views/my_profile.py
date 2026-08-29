from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from apps.core.models import Player
from apps.pods.mixins import PodMemberRequiredMixin


class MyProfileRedirectView(PodMemberRequiredMixin, View):
    """
    Atalho "Meu Perfil" da navbar: manda pro Player do usuário logado
    dentro deste pod. Se por algum motivo ele ainda não tiver um (ex: foi
    removido manualmente), manda pro cadastro de jogador.
    """

    def get(self, request, *args, **kwargs):
        player = Player.objects.filter(pod=self.pod, user=request.user).first()
        if player:
            return redirect("core:player-profile", pod_slug=self.pod.slug, pk=player.pk)
        return redirect(reverse("core:player-create", kwargs={"pod_slug": self.pod.slug}))
