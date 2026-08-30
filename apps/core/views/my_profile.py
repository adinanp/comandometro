from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View
from apps.core.forms import PlayerForm, PlayerProfileForm, UserEmailForm
from apps.core.models import Player, PlayerProfile
from apps.pods.mixins import PodMemberRequiredMixin


class MyProfileView(PodMemberRequiredMixin, View):
    """
    "Meu Perfil" — edita o Player do usuário logado neste pod (nome,
    apelido) e o PlayerProfile associado (pronomes, cor/wincon favorita).
    Todo membro ganha um Player automaticamente ao entrar no pod
    (CreatePodUseCase/JoinPodUseCase); não achar um aqui é um estado que
    não deveria acontecer.
    """

    template_name = "core/my_profile.html"

    def get(self, request, *args, **kwargs):
        player = self._get_player()
        if player is None:
            messages.error(request, "Não encontramos seu jogador neste pod.")
            return redirect("core:dashboard", pod_slug=self.pod.slug)
        profile = self._get_or_build_profile(player)
        return self._render(
            PlayerForm(instance=player),
            PlayerProfileForm(instance=profile),
            UserEmailForm(instance=request.user),
        )

    def post(self, request, *args, **kwargs):
        player = self._get_player()
        if player is None:
            messages.error(request, "Não encontramos seu jogador neste pod.")
            return redirect("core:dashboard", pod_slug=self.pod.slug)
        profile = self._get_or_build_profile(player)
        player_form = PlayerForm(request.POST, instance=player)
        profile_form = PlayerProfileForm(request.POST, instance=profile)
        email_form = UserEmailForm(request.POST, instance=request.user)
        if player_form.is_valid() and profile_form.is_valid() and email_form.is_valid():
            player_form.save()
            profile_form.instance.player = player
            profile_form.save()
            email_form.save()
            messages.success(request, "Perfil atualizado.")
            return redirect("core:my-profile", pod_slug=self.pod.slug)
        return self._render(player_form, profile_form, email_form)

    def _get_player(self):
        return Player.objects.filter(pod=self.pod, user=self.request.user).first()

    def _get_or_build_profile(self, player):
        return PlayerProfile.objects.filter(player=player).first() or PlayerProfile(
            player=player
        )

    def _render(self, player_form, profile_form, email_form):
        return render(
            self.request,
            self.template_name,
            {
                "pod": self.pod,
                "membership": self.membership,
                "player_form": player_form,
                "profile_form": profile_form,
                "email_form": email_form,
            },
        )
