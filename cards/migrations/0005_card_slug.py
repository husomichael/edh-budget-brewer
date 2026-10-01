"""Add Card.slug and backfill it, for readable share URLs (#21).

The backfill matters: without it every existing row has an empty slug and
every shared link 404s until the next `sync_cards`. SlugField carries
db_index=True by default, so the lookup index comes with the AddField.

slugify is inlined rather than imported from cards.slugs on purpose -- a
migration has to keep producing the same result years from now, even if the
application helper changes.
"""

from django.db import migrations, models
from django.utils.text import slugify

BATCH_SIZE = 2000


def backfill_slugs(apps, schema_editor):
    Card = apps.get_model("cards", "Card")
    batch = []
    for card in Card.objects.only("id", "name").iterator(chunk_size=BATCH_SIZE):
        card.slug = slugify(card.name)[:320]
        batch.append(card)
        if len(batch) >= BATCH_SIZE:
            Card.objects.bulk_update(batch, ["slug"])
            batch.clear()
    if batch:
        Card.objects.bulk_update(batch, ["slug"])


def clear_slugs(apps, schema_editor):
    """Reverse is a no-op beyond the column being dropped by AddField."""


class Migration(migrations.Migration):
    dependencies = [
        ("cards", "0004_deck_collectionitem_deckcard"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="slug",
            field=models.SlugField(blank=True, max_length=320),
        ),
        migrations.RunPython(backfill_slugs, clear_slugs),
    ]
