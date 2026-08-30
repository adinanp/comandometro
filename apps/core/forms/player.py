from django import forms
from django.contrib.auth import get_user_model
from apps.core.models import Player, PlayerProfile, PronounChoices

User = get_user_model()


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name", "nickname"]
        labels = {"name": "Nome", "nickname": "Apelido"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "nickname": forms.TextInput(attrs={"class": "form-input"}),
        }


class PlayerProfileForm(forms.ModelForm):
    class Meta:
        model = PlayerProfile
        fields = ["pronouns", "custom_pronouns", "favorite_color", "favorite_wincon"]
        labels = {
            "pronouns": "Pronomes",
            "custom_pronouns": "Pronomes (se \"Outro\")",
            "favorite_color": "Cor favorita",
            "favorite_wincon": "Wincon favorita",
        }
        widgets = {
            "pronouns": forms.Select(attrs={"class": "form-input"}),
            "custom_pronouns": forms.TextInput(attrs={"class": "form-input"}),
            "favorite_color": forms.TextInput(attrs={"class": "form-input"}),
            "favorite_wincon": forms.TextInput(attrs={"class": "form-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pronouns"].choices = [("", "Prefiro não dizer")] + list(
            PronounChoices.choices
        )


class UserEmailForm(forms.ModelForm):
    """
    Login é por username, não por e-mail — este campo é só uma forma
    opcional de a pessoa deixar um contato registrado, editável em "Meu
    Perfil". Sem verificação de endereço.
    """

    class Meta:
        model = User
        fields = ["email"]
        labels = {"email": "E-mail"}
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-input"}),
        }
