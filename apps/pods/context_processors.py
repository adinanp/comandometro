from apps.pods.models import Pod


def user_pods(request):
    """Disponibiliza `user_pods` em todo template, pro seletor de pod na navbar."""
    if not request.user.is_authenticated:
        return {}
    return {"user_pods": Pod.objects.filter(memberships__user=request.user).order_by("name")}
