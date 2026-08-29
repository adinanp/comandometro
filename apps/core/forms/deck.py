from django import forms
from apps.cards.models import Card
from apps.core.models import Deck, Player


class DeckForm(forms.ModelForm):
    class Meta:
        model = Deck
        fields = ["player", "commanders", "is_active"]
        widgets = {
            "commanders": forms.SelectMultiple(attrs={"class": "form-input", "size": 10}),
        }

    def __init__(self, *args, pod=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pod = pod
        self.fields["player"].queryset = Player.objects.filter(pod=pod).order_by("name")
        self.fields["commanders"].queryset = Card.objects.filter(
            is_commander_eligible=True
        ).order_by("name")

    def clean_commanders(self):
        commanders = list(self.cleaned_data.get("commanders", []))
        Deck.validate_commanders(commanders)
        return commanders

    def clean_player(self):
        player = self.cleaned_data["player"]
        if player.pod_id != self.pod.id:
            raise forms.ValidationError("Jogador não pertence a este pod.")
        return player
