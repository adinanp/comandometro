from apps.core.models import Player
from apps.core.use_cases.base import BaseUseCase
from apps.pods.models import Membership, Pod
from .create_pod import default_player_name


class JoinPodUseCase(BaseUseCase):
    """
    Resgata um convite: acha o Pod pelo `invite_token`, cria a Membership
    de `user` como membro comum (se ainda não existir) e o Player
    correspondente. Levanta Pod.DoesNotExist se o token não corresponder
    a nenhum pod.
    """

    def perform_request(self, user, invite_token) -> Pod:
        pod = Pod.objects.get(invite_token=invite_token)

        membership, created = Membership.objects.get_or_create(
            pod=pod, user=user, defaults={"role": Membership.Role.MEMBER}
        )
        if created:
            Player.objects.get_or_create(
                pod=pod, user=user, defaults={"name": default_player_name(user)}
            )
        return pod
