from django.contrib import admin

from cards.models import Card


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    """Read-only browser for synced Scryfall data.

    Cards are not editable here: `sync_cards` would silently overwrite any
    hand-edit on the next run, which is a confusing way to lose work.
    """

    list_display = (
        "name",
        "mana_cost",
        "type_line",
        "price_display",
        "edhrec_rank",
        "can_be_commander",
    )
    list_filter = (
        "legal_commander",
        "is_banned",
        "can_be_commander",
        "is_land",
        "is_basic",
        "layout",
    )
    search_fields = ("name", "type_line", "oracle_text")
    ordering = ("edhrec_rank",)
    list_per_page = 50

    readonly_fields = [f.name for f in Card._meta.fields]

    @admin.display(description="price", ordering="price_cents")
    def price_display(self, obj):
        return obj.price_dollars or "--"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
