from django import forms

from apps.core.models import Player
from apps.core.use_cases.draw_themes import PLAYERS_PER_DRAW


class ThemeDrawForm(forms.Form):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Jogadores",
    )

    def __init__(self, *args, pod, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["players"].queryset = Player.objects.filter(pod=pod).order_by("name")

    def clean_players(self):
        players = self.cleaned_data["players"]
        if len(players) != PLAYERS_PER_DRAW:
            raise forms.ValidationError(f"Escolha exatamente {PLAYERS_PER_DRAW} jogadores.")
        return players
