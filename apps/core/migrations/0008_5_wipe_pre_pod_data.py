from django.db import migrations


def wipe_existing_data(apps, schema_editor):
    """
    O projeto vira multi-tenant (Pod) a partir daqui, e os dados que
    existiam antes (times/decks/partidas de teste, sem pod nenhum) não têm
    como ser atribuídos a um pod real — foram descartados por decisão
    explícita, não migrados. `Player`/`Game` cascadeiam pra Deck,
    GameParticipant e Achievement, então apagar só os dois já limpa tudo.

    Isso precisa ser uma migration própria, separada da que adiciona as
    colunas `pod` (AddField mais adiante) — o Postgres recusa um
    `ALTER TABLE` numa tabela que acabou de sofrer um DELETE com gatilhos
    de FK pendentes dentro da mesma transação
    ("cannot ALTER TABLE ... because it has pending trigger events").
    """
    Game = apps.get_model("core", "Game")
    Player = apps.get_model("core", "Player")
    Player.objects.all().delete()
    Game.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_remove_card_is_partner_eligible_and_more'),
    ]

    operations = [
        migrations.RunPython(wipe_existing_data, reverse_code=migrations.RunPython.noop),
    ]
