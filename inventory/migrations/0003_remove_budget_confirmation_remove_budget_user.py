# Generated by Django 5.1.4 on 2025-01-07 14:58

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='budget',
            name='confirmation',
        ),
        migrations.RemoveField(
            model_name='budget',
            name='user',
        ),
    ]