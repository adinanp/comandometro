from django import forms
from django.forms import formset_factory

from apps.cards.models import Card
from apps.core.models import Deck, Game, GameParticipant, Player


class GameForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = ["date", "win_condition", "turn_count", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-input"}),
            "win_condition": forms.Select(attrs={"class": "form-input"}),
            "turn_count": forms.NumberInput(attrs={"class": "form-input", "min": 0}),
            "notes": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }


class GameParticipantForm(forms.Form):
    player = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    deck = forms.ModelChoiceField(
        queryset=Deck.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    placement = forms.IntegerField(
        min_value=1, widget=forms.NumberInput(attrs={"class": "form-input"})
    )
    kill_count = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    mvp_card_name = forms.CharField(
        required=False,
        label="Carta MVP (nome exato)",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    peak_life_total = forms.IntegerField(
        required=False,
        label="Vida mais alta",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    board_wipes_count = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    counterspell_count = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    complaint_count = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    is_self_elimination = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "h-4 w-4"})
    )
    biggest_creature_name = forms.CharField(
        required=False,
        label="Maior criatura (nome exato)",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    biggest_creature_power = forms.IntegerField(
        required=False,
        label="Poder",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    starting_seat = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    felt_salty = forms.BooleanField(
        required=False,
        label="Ficou salty",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
    )
    fun_rating = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=None,
        choices=[("", "-")] + [(n, n) for n in range(1, 6)],
        label="Nota de diversão",
        widget=forms.Select(attrs={"class": "form-input"}),
    )

    def __init__(self, *args, pod=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pod = pod
        self.fields["player"].queryset = Player.objects.filter(pod=pod).order_by("name")
        self.fields["deck"].queryset = Deck.objects.filter(player__pod=pod).order_by(
            "player__name"
        )

    def _resolve_card(self, field_name):
        name = self.cleaned_data.get(field_name)
        if not name:
            return None
        card = Card.objects.filter(name__iexact=name.strip()).first()
        if card is None:
            raise forms.ValidationError(f'Carta "{name}" não encontrada.')
        return card

    def clean_mvp_card_name(self):
        return self._resolve_card("mvp_card_name")

    def clean_biggest_creature_name(self):
        return self._resolve_card("biggest_creature_name")

    def clean(self):
        cleaned_data = super().clean()
        player = cleaned_data.get("player")
        deck = cleaned_data.get("deck")
        if player and deck and deck.player_id != player.id:
            raise forms.ValidationError("O deck selecionado não pertence a este jogador.")
        return cleaned_data


GameParticipantFormSet = formset_factory(
    GameParticipantForm, extra=4, min_num=2, validate_min=True
)


def build_participants(game, formset):
    """Cria os GameParticipant a partir de um GameParticipantFormSet válido."""
    participants = []
    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue
        data = form.cleaned_data
        participants.append(
            GameParticipant.objects.create(
                game=game,
                player=data["player"],
                deck=data.get("deck"),
                placement=data["placement"],
                kill_count=data.get("kill_count") or 0,
                mvp_card=data.get("mvp_card_name"),
                peak_life_total=data.get("peak_life_total"),
                board_wipes_count=data.get("board_wipes_count") or 0,
                counterspell_count=data.get("counterspell_count") or 0,
                complaint_count=data.get("complaint_count") or 0,
                is_self_elimination=data.get("is_self_elimination", False),
                biggest_creature=data.get("biggest_creature_name"),
                biggest_creature_power=data.get("biggest_creature_power"),
                starting_seat=data.get("starting_seat"),
                felt_salty=data.get("felt_salty", False),
                fun_rating=data.get("fun_rating"),
            )
        )
    return participants
