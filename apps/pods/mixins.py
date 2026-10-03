from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Membership, Pod


def _resolve_membership(request, pod_slug):
    pod = get_object_or_404(Pod, slug=pod_slug)
    membership = Membership.objects.filter(pod=pod, user=request.user).first()
    if membership is None:
        raise Http404
    return pod, membership


class PodMemberRequiredMixin:
    """
    Resolve o Pod a partir de `pod_slug` na URL e garante que o usuário
    autenticado é membro dele. Views de apps/core herdam disso e ganham
    `self.pod` e `self.membership` prontos antes do handler (get/post) rodar.
    Quem não está logado é redirecionado pro login; logado mas não membro
    (ou pod inexistente) recebe 404, pra não revelar que o pod existe.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.pod, self.membership = _resolve_membership(request, kwargs["pod_slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pod"] = self.pod
        context["membership"] = self.membership
        return context


class PodOwnerRequiredMixin:
    """Igual a PodMemberRequiredMixin, mas exige role=OWNER."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.pod, self.membership = _resolve_membership(request, kwargs["pod_slug"])
        if not self.membership.is_owner:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pod"] = self.pod
        context["membership"] = self.membership
        return context
