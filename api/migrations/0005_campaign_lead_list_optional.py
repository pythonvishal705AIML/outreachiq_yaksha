# Generated migration to make lead_list_id optional in campaigns table

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_aiprompttemplate_versioning'),
    ]

    operations = [
        migrations.AlterField(
            model_name='campaign',
            name='lead_list_id',
            field=models.CharField(max_length=255, blank=True, null=True),
        ),
    ]
