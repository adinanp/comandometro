from django import forms
from django.forms import formset_factory

from apps.core.models import Achievement, Player


class AchievementForm(forms.Form):
    existing_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    player = forms.ModelChoiceField(
        queryset=Player.objects.none(),
        required=False,
        label="Jogador",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    title = forms.CharField(
        required=False,
        label="Feito",
        help_text='Ex: "Maior Torment of Hailfire", "Matar com Sign in Blood".',
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    detail = forms.CharField(
        required=False,
        label="Detalhe",
        help_text='Ex: "X=34", "Adinan matou Alex".',
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )

    def __init__(self, *args, pod=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["player"].queryset = Player.objects.filter(pod=pod).order_by("name")
        self.fields["player"].empty_label = "Selecione um jogador"

    def clean(self):
        cleaned_data = super().clean()
        player = cleaned_data.get("player")
        title = cleaned_data.get("title")
        if title and not player:
            raise forms.ValidationError("Selecione o jogador que fez esse feito.")
        if player and not title:
            raise forms.ValidationError("Descreva o feito, ou deixe a linha em branco.")
        return cleaned_data


# Sempre começa vazio — o "+" no formulário adiciona linhas dinamicamente
# via JS (ver core/game_form.html), em vez de um número fixo de linhas.
AchievementFormSet = formset_factory(AchievementForm, extra=0, min_num=0)


def save_achievements(game, formset):
    """
    Cria/atualiza/remove os Achievement de uma partida a partir de um
    AchievementFormSet válido — mesmo padrão de upsert de
    `save_participants`. Uma linha existente que sumiu do formset (botão
    "Remover" na edição) é apagada; como todos os campos são opcionais,
    isso nunca colide com validação de campo obrigatório.
    """
    seen_ids = set()
    achievements = []
    for form in formset:
        if not form.cleaned_data or not form.cleaned_data.get("title"):
            continue
        data = form.cleaned_data
        fields = dict(
            player=data["player"],
            title=data["title"],
            detail=data.get("detail", ""),
        )
        existing_id = data.get("existing_id")
        if existing_id:
            Achievement.objects.filter(pk=existing_id, game=game).update(**fields)
            seen_ids.add(existing_id)
            achievements.append(existing_id)
        else:
            achievement = Achievement.objects.create(game=game, date=game.date, **fields)
            seen_ids.add(achievement.pk)
            achievements.append(achievement)

    game.achievements.exclude(pk__in=seen_ids).delete()
    return achievements
