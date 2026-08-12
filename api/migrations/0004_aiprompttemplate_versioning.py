import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_aiprompttemplate_ai_params'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIPromptTemplateVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version_number', models.IntegerField()),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('category', models.CharField(max_length=30)),
                ('template_text', models.TextField()),
                ('variables', models.JSONField(default=list)),
                ('model_name', models.CharField(max_length=100)),
                ('temperature', models.FloatField()),
                ('max_tokens', models.IntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('template', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='versions',
                    to='api.aiprompttemplate',
                )),
            ],
            options={
                'db_table': 'ai_prompt_template_versions',
                'ordering': ['-version_number'],
                'unique_together': {('template', 'version_number')},
            },
        ),
    ]
