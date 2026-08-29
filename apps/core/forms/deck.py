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
        return cleaned_data

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
