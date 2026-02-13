from django.urls import path
from . import views

urlpatterns = [
  path("", views.election_list, name="election_list"),
path("elections/new/", views.election_create, name="election_create"),
path("elections/<int:pk>/", views.election_detail, name="election_detail"),
path("elections/<int:pk>/edit/", views.election_update, name="election_update"),
path("elections/<int:pk>/delete/", views.election_delete, name="election_delete"),




    path("elections/<int:election_id>/governorates/<int:gov_id>/", views.governorate_detail, name="governorate_detail"),
    path("districts/<int:district_id>/", views.district_detail, name="district_detail"),
    path("subdistricts/<int:subdistrict_id>/", views.subdistrict_detail, name="subdistrict_detail"),
    path("units/<int:unit_id>/", views.unit_detail, name="unit_detail"),

    path("elections/<int:election_id>/governorates/<int:gov_id>/upload-geo/", views.upload_geo, name="upload_geo"),
    path("elections/<int:election_id>/governorates/<int:gov_id>/upload-votes/", views.upload_votes, name="upload_votes"),

    path("elections/<int:election_id>/governorates/<int:gov_id>/public/", views.governorate_public, name="governorate_public"),

    path("elections/<int:election_id>/governorates/<int:gov_id>/special/", views.governorate_special, name="governorate_special"),

   path(
    "elections/<int:election_id>/special/unit/<int:unit_id>/",
    views.special_unit_detail,
    name="special_unit_detail"
)


   

]