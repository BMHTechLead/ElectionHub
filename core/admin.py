from django.contrib import admin
from .models import (
    Election,
    Governorate,
    District,
    SubDistrict,
    ElectionUnit,
    VoteRecord,
)


# -------------------------------
# Election
# -------------------------------
@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "election_type",
        "status",
        "election_date",
        "created_at",
    )
    list_filter = ("election_type", "status", "election_date")
    search_fields = ("name",)
    ordering = ("-id",)
    readonly_fields = ("created_at",)


# -------------------------------
# Governorate
# -------------------------------
@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "election")
    list_filter = ("election",)
    search_fields = ("name",)
    ordering = ("election", "name")


# -------------------------------
# District
# -------------------------------
@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "governorate")
    list_filter = ("governorate__election", "governorate")
    search_fields = ("name",)
    ordering = ("governorate", "name")


# -------------------------------
# SubDistrict
# -------------------------------
@admin.register(SubDistrict)
class SubDistrictAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "district")
    list_filter = ("district__governorate__election", "district")
    search_fields = ("name",)
    ordering = ("district", "name")


# -------------------------------
# Election Unit
# -------------------------------
@admin.register(ElectionUnit)
class ElectionUnitAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "election_unit_number",
        "election_unit_name",
        "governorate",
        "district",
        "subdistrict",
        "election",
    )
    list_filter = (
        "election",
        "governorate",
        "district",
        "subdistrict",
    )
    search_fields = (
        "election_unit_number",
        "election_unit_name",
        "election_unit_address",
    )
    ordering = ("election", "governorate", "district", "election_unit_number")
    list_per_page = 50


# -------------------------------
# Vote Record
# -------------------------------
@admin.register(VoteRecord)
class VoteRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "election",
        "governorate",
        "election_unit",
        "list_number",
        "candidate_name",
        "voting_type",
        "number_of_votes",
    )

    list_filter = (
        "election",
        "governorate",
        "voting_type",
        "list_number",
    )

    search_fields = (
        "candidate_name",
        "candidate_number",
        "list_name",
        "list_number",
        "election_unit__election_unit_number",
    )

    ordering = ("election", "governorate", "-number_of_votes")

    list_per_page = 100

    # performance optimization
    autocomplete_fields = ("election_unit",)