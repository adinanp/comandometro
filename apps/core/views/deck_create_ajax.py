from django.http import JsonResponse
from django.views import View
from apps.core.forms import DeckForm
from apps.pods.mixins import PodMemberRequiredMixin


class DeckCreateAjaxView(PodMemberRequiredMixin, View):
    """
    Mesma criação de deck de DeckCreateView, mas devolve JSON em vez de
    redirecionar — usado pelo modal "criar novo deck" dentro do formulário
    de partida, pra não perder o que já foi preenchido nas outras linhas.
    """

    def post(self, request, *args, **kwargs):
        form = DeckForm(request.POST, pod=self.pod, prefix="new_deck")
        if form.is_valid():
            deck = form.save()
            return JsonResponse({"id": deck.id, "name": str(deck)})

        errors = []
        for field_name, field_errors in form.errors.items():
            field = form.fields.get(field_name)
            label = field.label if field else "Erro"
            errors.append(f"{label}: {' '.join(field_errors)}")
        return JsonResponse({"errors": errors}, status=400)
