from django import forms
from django.forms import formset_factory

from apps.core.models import Achievement, Player


class AchievementForm(forms.Form):
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


AchievementFormSet = formset_factory(AchievementForm, extra=2, min_num=0)


def build_achievements(game, formset):
    """Cria os Achievement a partir de um AchievementFormSet válido."""
    achievements = []
    for form in formset:
        if not form.cleaned_data or not form.cleaned_data.get("title"):
            continue
        data = form.cleaned_data
        achievements.append(
            Achievement.objects.create(
                player=data["player"],
                game=game,
                title=data["title"],
                detail=data.get("detail", ""),
                date=game.date,
            )
        )
    return achievements
