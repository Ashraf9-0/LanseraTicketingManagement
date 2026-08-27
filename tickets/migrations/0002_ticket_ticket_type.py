from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='ticket_type',
            field=models.CharField(
                choices=[('early_bird', 'Early Bird'), ('regular', 'Regular'), ('vip', 'VIP')],
                default='regular',
                max_length=20,
            ),
        ),
    ]