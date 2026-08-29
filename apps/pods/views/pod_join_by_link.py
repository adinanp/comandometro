import re

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


class PodJoinByLinkView(LoginRequiredMixin, View):
    """Aceita colar a URL inteira do convite (ou só o token) e redireciona."""

    def get(self, request):
        pasted = request.GET.get("link", "")
        match = UUID_RE.search(pasted)
        if not match:
            messages.error(request, "Link de convite inválido.")
            return redirect("pods:pod-list")
        return redirect("pods:pod-join", token=match.group(0))
