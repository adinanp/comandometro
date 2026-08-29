from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from apps.core.forms import PlayerForm, PlayerProfileForm
from apps.core.models import Player, PlayerProfile
from apps.pods.mixins import PodMemberRequiredMixin


class MyProfileView(PodMemberRequiredMixin, View):
    """
    "Meu Perfil" — edita o Player do usuário logado neste pod (nome,
    apelido) e o PlayerProfile associado (pronomes, cor/wincon favorita).
    Se o usuário ainda não tiver um Player neste pod, manda pro cadastro.
    """

    template_name = "core/my_profile.html"

    def get(self, request, *args, **kwargs):
        player = self._get_player()
        if player is None:
            return redirect(
                reverse("core:player-create", kwargs={"pod_slug": self.pod.slug})
            )
        profile = self._get_or_build_profile(player)
        return self._render(PlayerForm(instance=player), PlayerProfileForm(instance=profile))

    def post(self, request, *args, **kwargs):
        player = self._get_player()
        if player is None:
            return redirect(
                reverse("core:player-create", kwargs={"pod_slug": self.pod.slug})
            )
        profile = self._get_or_build_profile(player)
        player_form = PlayerForm(request.POST, instance=player)
        profile_form = PlayerProfileForm(request.POST, instance=profile)
        if player_form.is_valid() and profile_form.is_valid():
            player_form.save()
            profile_form.instance.player = player
            profile_form.save()
            messages.success(request, "Perfil atualizado.")
            return redirect("core:my-profile", pod_slug=self.pod.slug)
        return self._render(player_form, profile_form)

    def _get_player(self):
        return Player.objects.filter(pod=self.pod, user=self.request.user).first()

    def _get_or_build_profile(self, player):
        return PlayerProfile.objects.filter(player=player).first() or PlayerProfile(
            player=player
        )

    def _render(self, player_form, profile_form):
        return render(
            self.request,
            self.template_name,
            {
                "pod": self.pod,
                "membership": self.membership,
                "player_form": player_form,
                "profile_form": profile_form,
            },
        )
