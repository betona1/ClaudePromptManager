from django.db import migrations


def migrate_chat_ids(apps, schema_editor):
    """Move existing TelegramBot.chat_id to TelegramChatId model."""
    TelegramBot = apps.get_model('core', 'TelegramBot')
    TelegramChatId = apps.get_model('core', 'TelegramChatId')
    for bot in TelegramBot.objects.exclude(chat_id='').exclude(chat_id__isnull=True):
        TelegramChatId.objects.get_or_create(
            bot=bot,
            chat_id=bot.chat_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_add_telegram_chat_id_model'),
    ]

    operations = [
        migrations.RunPython(migrate_chat_ids, migrations.RunPython.noop),
    ]
