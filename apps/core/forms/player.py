from django import forms
from apps.core.models import Player


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name", "nickname"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "nickname": forms.TextInput(attrs={"class": "form-input"}),
        }
