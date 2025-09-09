from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_initial'),
        ('users', '0001_initial'),  # Adjust this based on your users app's initial migration
    ]

    operations = [
        migrations.AddField(
            model_name='productionlogs',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='users.branch',
            ),
        ),
    ]
