from django import forms
from django.utils.html import format_html

from .models import Card


class CardPickerWidget(forms.Widget):
    """
    Campo de busca de carta (nome) em vez de um <select> com milhares de
    opções. Renderiza um input de texto + um input escondido com o ID da
    carta selecionada; a busca em si roda via JS (ver `card-picker` em
    templates/base.html) contra `cards:card-search`.
    """

    def __init__(self, commander_only=False, role="", attrs=None):
        self.commander_only = commander_only
        self.role = role
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        card_name = ""
        if value:
            card_name = Card.objects.filter(pk=value).values_list("name", flat=True).first() or ""

        attrs = attrs or {}
        widget_id = attrs.get("id", f"id_{name}")

        return format_html(
            '<div class="card-picker" data-commander-only="{}" data-role="{}">'
            '<input type="text" class="form-input card-picker-input" autocomplete="off" '
            'placeholder="Buscar carta pelo nome..." value="{}">'
            '<input type="hidden" name="{}" id="{}" class="card-picker-value" value="{}">'
            '<div class="card-picker-results"></div>'
            "</div>",
            "1" if self.commander_only else "",
            self.role,
            card_name,
            name,
            widget_id,
            value or "",
        )

    def value_from_datadict(self, data, files, name):
        return data.get(name) or None
