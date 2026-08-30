from django import forms
from django.forms import formset_factory

from apps.cards.models import Card
from apps.cards.widgets import CardPickerWidget
from apps.core.models import (
    Deck,
    Game,
    GameParticipant,
    Player,
    resolve_win_condition,
    wincon_label,
)


class DeckByPlayerSelect(forms.Select):
    """
    <select> de Deck com `data-player-id` em cada <option>, pro JS filtrar
    os decks pelo jogador escolhido na mesma linha do formset sem precisar
    de ida ao servidor — ver core/game_form.html.
    """

    def __init__(self, player_by_deck=None, attrs=None):
        self.player_by_deck = player_by_deck or {}
        super().__init__(attrs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        raw_value = getattr(value, "value", value)
        player_id = self.player_by_deck.get(raw_value)
        if player_id:
            option["attrs"]["data-player-id"] = player_id
        return option


class GameForm(forms.ModelForm):
    win_condition = forms.CharField(
        required=True,
        label="Condição de vitória",
        help_text="Escolha uma sugestão ou digite uma wincon nova.",
        widget=forms.TextInput(
            attrs={"class": "form-input", "list": "wincon-datalist", "autocomplete": "off"}
        ),
    )

    class Meta:
        model = Game
        fields = ["date", "win_condition", "turn_count", "notes"]
        labels = {
            "date": "Data",
            "turn_count": "Contagem de turnos",
            "notes": "Notas",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-input"}),
            "turn_count": forms.NumberInput(attrs={"class": "form-input", "min": 0}),
            "notes": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].required = True
        if self.instance and self.instance.pk:
            self.fields["win_condition"].initial = wincon_label(self.instance.win_condition)

    def clean_win_condition(self):
        return resolve_win_condition(self.cleaned_data["win_condition"])


class GameParticipantForm(forms.Form):
    existing_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    player = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        label="Jogador",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    deck = forms.ModelChoiceField(
        queryset=Deck.objects.none(),
        required=False,
        label="Deck",
        widget=DeckByPlayerSelect(attrs={"class": "form-input"}),
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
        decks = list(Deck.objects.filter(player__pod=pod).order_by("player__name"))
        self.fields["deck"].queryset = Deck.objects.filter(
            pk__in=[d.pk for d in decks]
        ).order_by("player__name")
        self.fields["deck"].empty_label = "Sem deck definido"
        self.fields["deck"].widget.player_by_deck = {d.pk: d.player_id for d in decks}

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


def save_participants(game, formset):
    """
    Cria/atualiza os GameParticipant a partir de um GameParticipantFormSet
    válido. Linhas com `existing_id` (pré-carregado na edição de uma
    partida) atualizam o participante existente; as demais criam um novo
    — a mesma função serve tanto pra criar quanto pra editar uma partida.
    """
    participants = []
    for form in formset:
        if not form.cleaned_data or not form.cleaned_data.get("player"):
            continue
        data = form.cleaned_data
        fields = dict(
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
        existing_id = data.get("existing_id")
        if existing_id:
            GameParticipant.objects.filter(pk=existing_id, game=game).update(**fields)
            participants.append(existing_id)
        else:
            participants.append(
                GameParticipant.objects.create(game=game, **fields)
            )
    return participants
