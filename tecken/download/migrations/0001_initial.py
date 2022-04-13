# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Generated by Django 1.11.6 on 2017-10-10 21:11

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MissingSymbol",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("hash", models.CharField(max_length=32, unique=True)),
                ("symbol", models.CharField(max_length=150)),
                ("debugid", models.CharField(max_length=150)),
                ("filename", models.CharField(max_length=150)),
                ("code_file", models.CharField(max_length=50, null=True)),
                ("code_id", models.CharField(max_length=50, null=True)),
                ("count", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True, db_index=True)),
            ],
        ),
    ]
