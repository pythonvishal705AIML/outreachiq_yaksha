from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_ai_prompt_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiprompttemplate',
            name='model_name',
            field=models.CharField(default='gpt-4o-mini', max_length=100),
        ),
        migrations.AddField(
            model_name='aiprompttemplate',
            name='temperature',
            field=models.FloatField(default=0.7),
        ),
        migrations.AddField(
            model_name='aiprompttemplate',
            name='max_tokens',
            field=models.IntegerField(default=500),
        ),
    ]
