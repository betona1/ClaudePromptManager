from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_migrate_telegram_chat_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='prompt',
            name='tmux_session',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='tmux/screen session name captured at prompt time',
                max_length=100,
                null=True,
            ),
        ),
    ]
