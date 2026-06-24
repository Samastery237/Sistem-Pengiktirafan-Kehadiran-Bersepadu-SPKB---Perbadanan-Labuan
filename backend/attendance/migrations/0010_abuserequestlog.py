import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0009_failedloginattempt_adminprofile_email_verified_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AbuseRequestLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(db_index=True)),
                ('window_start', models.DateTimeField(default=django.utils.timezone.now)),
                ('request_count', models.IntegerField(default=1)),
                ('is_blocked', models.BooleanField(default=False)),
                ('blocked_until', models.DateTimeField(blank=True, null=True)),
                ('last_request_path', models.CharField(blank=True, max_length=500)),
                ('user_agent', models.TextField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Abuse Request Log',
                'verbose_name_plural': 'Abuse Request Logs',
                'ordering': ['-window_start'],
            },
        ),
    ]
