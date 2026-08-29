from django import forms
from django.forms import formset_factory

from apps.cards.models import Card
from apps.cards.widgets import CardPickerWidget
from apps.core.models import Deck, Game, GameParticipant, Player, WinConditionChoices


class GameForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = ["date", "win_condition", "turn_count", "notes"]
        labels = {
            "date": "Data",
            "win_condition": "Condição de vitória",
            "turn_count": "Contagem de turnos",
            "notes": "Notas",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-input"}),
            "win_condition": forms.Select(attrs={"class": "form-input"}),
            "turn_count": forms.NumberInput(attrs={"class": "form-input", "min": 0}),
            "notes": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].required = True
        self.fields["win_condition"].required = True
        self.fields["win_condition"].choices = [("", "Selecione uma opção")] + list(
            WinConditionChoices.choices
        )


class GameParticipantForm(forms.Form):
    player = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        label="Jogador",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    deck = forms.ModelChoiceField(
        queryset=Deck.objects.none(),
        required=False,
        label="Deck",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    placement = forms.IntegerField(
        min_value=1,
        required=False,
        label="Colocação",
        help_text="1º lugar = quem venceu, 2º = seguinte, e assim por diante.",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    kill_count = forms.IntegerField(
        min_value=0,
        required=False,
        label="Eliminações",
        help_text="Quantos outros jogadores esse participante eliminou na partida.",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    mvp_card = forms.ModelChoiceField(
        queryset=Card.objects.all(),
        required=False,
        label="Carta MVP",
        widget=CardPickerWidget(role="mvp-card"),
    )
    peak_life_total = forms.IntegerField(
        required=False,
        label="Vida mais alta",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    board_wipes_count = forms.IntegerField(
        min_value=0,
        required=False,
        label="Board wipes",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    counterspell_count = forms.IntegerField(
        min_value=0,
        required=False,
        label="Counterspells",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    complaint_count = forms.IntegerField(
        min_value=0,
        required=False,
        label="Reclamações",
        help_text="Quantas vezes esse jogador reclamou/espernenou durante a partida — é brincadeira do grupo, não julgamento.",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    is_self_elimination = forms.BooleanField(
        required=False,
        label="Suicídio",
        help_text="O participante se eliminou sozinho, sem ser por outro jogador.",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
    )
    starting_seat = forms.IntegerField(
        required=False,
        min_value=1,
        label="Posição inicial",
        help_text="Ordem de jogada na mesa (1 = primeiro a jogar naquela partida).",
        widget=forms.NumberInput(attrs={"class": "form-input"}),
    )
    felt_salty = forms.BooleanField(
        required=False,
        label="Ficou salty",
        help_text="Marque se ESSE jogador (que não venceu) achou a vitória de outro participante irritante.",
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
    )

    def __init__(self, *args, pod=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pod = pod
        self.fields["player"].queryset = Player.objects.filter(pod=pod).order_by("name")
        self.fields["player"].empty_label = "Selecione um jogador"
        self.fields["deck"].queryset = Deck.objects.filter(player__pod=pod).order_by(
            "player__name"
        )
        self.fields["deck"].empty_label = "Sem deck definido"

    def clean(self):
        cleaned_data = super().clean()
        player = cleaned_data.get("player")
        deck = cleaned_data.get("deck")
        if player and deck and deck.player_id != player.id:
            raise forms.ValidationError("O deck selecionado não pertence a este jogador.")
        return cleaned_data


GameParticipantFormSet = formset_factory(
    GameParticipantForm, extra=2, min_num=2, validate_min=True
)


def build_participants(game, formset):
    """Cria os GameParticipant a partir de um GameParticipantFormSet válido."""
    participants = []
    for form in formset:
        if not form.cleaned_data or not form.cleaned_data.get("player"):
            continue
        data = form.cleaned_data
        participants.append(
            GameParticipant.objects.create(
                game=game,
                player=data["player"],
                deck=data.get("deck"),
                placement=data.get("placement"),
                kill_count=data.get("kill_count") or 0,
                mvp_card=data.get("mvp_card"),
                peak_life_total=data.get("peak_life_total"),
                board_wipes_count=data.get("board_wipes_count") or 0,
                counterspell_count=data.get("counterspell_count") or 0,
                complaint_count=data.get("complaint_count") or 0,
                is_self_elimination=data.get("is_self_elimination", False),
                starting_seat=data.get("starting_seat"),
                felt_salty=data.get("felt_salty", False),
            )
        )
    return participants
