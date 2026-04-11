from django.db import migrations


def seed_cabinets(apps, schema_editor):
    Cabinet = apps.get_model("main", "Cabinet")

    ordered_names = [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
        "C8",
        "C9",
        "C10",
        "C11",
        "Lab1",
        "Lab2",
        "Lab3",
        "CH",
    ]
    skippable_names = {"Lab1", "Lab2", "Lab3"}

    for index, name in enumerate(ordered_names, start=1):
        Cabinet.objects.update_or_create(
            name=name,
            defaults={
                "sort_order": index * 10,
                "can_be_skipped": name in skippable_names,
                "included": True,
            },
        )


def remove_seeded_cabinets(apps, schema_editor):
    Cabinet = apps.get_model("main", "Cabinet")
    Cabinet.objects.filter(
        name__in=[
            "C1",
            "C2",
            "C3",
            "C4",
            "C5",
            "C6",
            "C7",
            "C8",
            "C9",
            "C10",
            "C11",
            "Lab1",
            "Lab2",
            "Lab3",
            "CH",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_cabinets, remove_seeded_cabinets),
    ]
