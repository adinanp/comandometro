from django import forms
from apps.cards.models import Card
from apps.cards.widgets import CardPickerWidget
from apps.core.models import Deck, Player


class DeckForm(forms.ModelForm):
    commander_1 = forms.ModelChoiceField(
        queryset=Card.objects.filter(is_commander_eligible=True),
        label="Comandante",
        widget=CardPickerWidget(commander_only=True, role="commander-1"),
    )
    commander_2 = forms.ModelChoiceField(
        queryset=Card.objects.filter(is_commander_eligible=True),
        label="2º Comandante (Partner)",
        required=False,
        widget=CardPickerWidget(commander_only=True, role="commander-2"),
    )

    class Meta:
        model = Deck
        fields = ["player", "is_active"]
        labels = {"player": "Jogador", "is_active": "Deck ativo"}
        widgets = {
            "player": forms.Select(attrs={"class": "form-input"}),
        }

    def __init__(self, *args, pod=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pod = pod
        self.fields["player"].queryset = Player.objects.filter(pod=pod).order_by("name")
        self.fields["player"].empty_label = "Selecione um jogador"

    def clean_player(self):
        player = self.cleaned_data["player"]
        if player.pod_id != self.pod.id:
            raise forms.ValidationError("Jogador não pertence a este pod.")
        return player

    def clean(self):
        cleaned_data = super().clean()
        commanders = [
            c for c in (cleaned_data.get("commander_1"), cleaned_data.get("commander_2")) if c
        ]
        if commanders:
            Deck.validate_commanders(commanders)
            player = cleaned_data.get("player")
            if player:
                self._validate_not_duplicate(player, commanders)
        return cleaned_data

    def _validate_not_duplicate(self, player, commanders):
        """
        Um jogador pode ter vários decks, mas nunca dois com exatamente os
        mesmos comandantes — evita o erro comum de clicar em "+ Criar deck"
        de novo em vez de escolher o deck já existente no dropdown.
        """
        wanted_ids = sorted(c.id for c in commanders)
        existing = Deck.objects.filter(player=player).prefetch_related("commanders")
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        for deck in existing:
            if sorted(deck.commanders.values_list("id", flat=True)) == wanted_ids:
                names = " / ".join(c.name for c in commanders)
                raise forms.ValidationError(
                    f'{player.name} já tem um deck com {names} — '
                    "selecione o deck existente em vez de criar outro igual."
                )

    def save(self, commit=True):
        deck = super().save(commit=commit)
        if deck.pk:
            commanders = [
                c
                for c in (self.cleaned_data.get("commander_1"), self.cleaned_data.get("commander_2"))
                if c
            ]
            deck.commanders.set(commanders)
        return deck
