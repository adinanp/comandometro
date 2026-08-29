from django import forms
from apps.pods.models import Pod


class PodForm(forms.ModelForm):
    class Meta:
        model = Pod
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Nome do playgroup"}
            ),
        }
