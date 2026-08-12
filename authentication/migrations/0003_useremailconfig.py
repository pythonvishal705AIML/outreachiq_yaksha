import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_usergmailtoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserEmailConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_email', models.EmailField(max_length=254)),
                ('from_name', models.CharField(blank=True, max_length=100)),
                ('smtp_host', models.CharField(default='smtp.gmail.com', max_length=100)),
                ('smtp_port', models.IntegerField(default=465)),
                ('app_password', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='email_config',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'user_email_configs',
            },
        ),
    ]
