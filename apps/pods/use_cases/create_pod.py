from apps.core.models import Player
from apps.core.use_cases.base import BaseUseCase
from apps.pods.models import Membership, Pod


class CreatePodUseCase(BaseUseCase):
    """
    Cria um Pod novo, torna `user` dono dele e cria automaticamente o
    Player desse usuário no roster do pod.
    """

    def perform_request(self, user, name) -> Pod:
        pod = Pod.objects.create(name=name)
        Membership.objects.create(pod=pod, user=user, role=Membership.Role.OWNER)
        Player.objects.create(pod=pod, user=user, name=default_player_name(user))
        return pod


def default_player_name(user):
    full_name = user.get_full_name()
    if full_name:
        return full_name
    if user.email:
        return user.email.split("@")[0]
    return user.username
