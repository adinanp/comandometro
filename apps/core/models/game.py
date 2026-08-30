from django.db import models


class WinConditionChoices(models.TextChoices):
    """
    As wincons "conhecidas" do sistema — usadas como sugestão no campo de
    texto livre do formulário de partida (ver GameForm) e nas métricas
    que dependem de uma wincon específica (maior combeiro/agressor/
    comandeiro). `Game.win_condition` aceita qualquer texto, não só estas
    — ver `resolve_win_condition()` mais abaixo.
    """

    COMBAT = "combat", "Combate"
    COMBO = "combo", "Combo"
    ENGINE_VALUE = "engine_value", "Engine/Value"
    INFECT = "infect", "Infect"
    SELF_MILL = "self_mill", "Self-Mill"
    HARD_LOCK = "hard_lock", "Hard Lock"
    MILL = "mill", "Mill"
    SOFT_LOCK = "soft_lock", "Soft Lock"
    BURN_LIFELOSS = "burn_lifeloss", "Queima/Perda de Vida"
    COMMANDER_DAMAGE = "commander_damage", "Dano de Comandante"


_WINCON_LABEL_TO_VALUE = {label.lower(): value for value, label in WinConditionChoices.choices}
_WINCON_VALUE_TO_LABEL = dict(WinConditionChoices.choices)


def resolve_win_condition(text):
    """
    Recebe o texto digitado/escolhido no formulário e devolve o valor a
    salvar: se bater (sem diferenciar maiúsculas) com o label de uma
    wincon conhecida, devolve o slug dela — pra continuar agrupando com
    o histórico existente. Senão, devolve o texto digitado como uma
    wincon nova/customizada.
    """
    text = text.strip()
    return _WINCON_LABEL_TO_VALUE.get(text.lower(), text)


def wincon_label(value):
    """Traduz uma wincon conhecida pro label em português; uma wincon
    customizada (texto livre) já é o próprio label, devolve como está."""
    return _WINCON_VALUE_TO_LABEL.get(value, value)


def wincon_suggestions(pod):
    """
    Sugestões pro <datalist> do campo de wincon: as pré-definidas mais
    qualquer wincon customizada que esse pod já tenha usado (traduzidas
    pro label, nunca o slug cru) — incentiva reaproveitar o mesmo nome em
    vez de fragmentar as estatísticas com grafias parecidas.
    """
    existing = (
        Game.objects.filter(pod=pod)
        .exclude(win_condition="")
        .values_list("win_condition", flat=True)
        .distinct()
    )
    labels = {wincon_label(value) for value in existing}
    labels.update(label for _, label in WinConditionChoices.choices)
    return sorted(labels)


class Game(models.Model):
    pod = models.ForeignKey(
        "pods.Pod", on_delete=models.CASCADE, related_name="games"
    )
    date = models.DateField(
        null=True, blank=True, help_text="Data em que a partida foi realizada"
    )
    win_condition = models.CharField(
        max_length=60,
        blank=True,
        help_text="Forma como o vencedor ganhou o jogo — pode ser uma das sugestões ou uma nova, digitada livremente",
    )
    notes = models.TextField(
        blank=True, help_text="Observações ou momentos marcantes da partida"
    )
    turn_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="Número de turnos até o fim da partida"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        date_str = self.date.strftime("%d/%m/%Y") if self.date else "Sem data"
        return f"Jogo #{self.pk} ({date_str})"

    def get_win_condition_display(self):
        """
        `win_condition` não tem mais `choices=` (é freeform — ver
        `resolve_win_condition()`), então o Django não gera esse método
        automaticamente; reimplementado aqui pra manter os templates que já
        chamavam `game.get_win_condition_display` funcionando sem alteração.
        """
        return wincon_label(self.win_condition)
