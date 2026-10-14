"""Seed the standard unit dictionary (reference data, ADR-011).

Metric units only; kitchen measures (tsp, tbsp, cup) are intentionally out of scope.
Idempotent: re-running updates rows by ``code``. Not reversed (units may be referenced).
"""

from decimal import Decimal

from django.db import migrations

UNITS = [
    # code, name, dimension, factor_to_base
    ("g", "Gram", "mass", Decimal("1")),
    ("kg", "Kilogram", "mass", Decimal("1000")),
    ("ml", "Millilitre", "volume", Decimal("1")),
    ("l", "Litre", "volume", Decimal("1000")),
    ("pcs", "Piece", "count", Decimal("1")),
]


def seed_units(apps, schema_editor):
    Unit = apps.get_model("catalog", "Unit")
    for code, name, dimension, factor in UNITS:
        Unit.objects.update_or_create(
            code=code,
            defaults={"name": name, "dimension": dimension, "factor_to_base": factor},
        )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [migrations.RunPython(seed_units, migrations.RunPython.noop)]
