from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum

import pandas as pd

from .models import Election, Governorate, District, SubDistrict, ElectionUnit, VoteRecord


# ---------- helpers ----------
def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    if "Unnamed: 13" in df.columns:
        df = df.drop(columns=["Unnamed: 13"])
    return df


def missing_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    return [c for c in required if c not in df.columns]


def safe_str(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def safe_int(x) -> int:
    try:
        if pd.isna(x) or x == "":
            return 0
        return int(float(x))
    except Exception:
        return 0


# ---------- pages ----------
@login_required
def election_list(request):
    elections = Election.objects.order_by("-id")
    return render(request, "core/election_list.html", {"elections": elections})


@login_required
def election_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        election_type = (request.POST.get("election_type") or "").strip()
        status = (request.POST.get("status") or "ACTIVE").strip()
        election_date = request.POST.get("election_date") or None

        if not name:
            messages.error(request, "Election name is required.")
            return redirect("election_create")

        if election_type not in ["IRAQ", "KRG"]:
            messages.error(request, "Invalid election type.")
            return redirect("election_create")

        if status not in ["ACTIVE", "FINISHED"]:
            messages.error(request, "Invalid status.")
            return redirect("election_create")

        e = Election.objects.create(
            name=name,
            election_type=election_type,
            status=status,
            election_date=election_date,
        )

        if election_type == "IRAQ":
            defaults = ["Slemani", "Erbil", "Duhok", "Kirkuk", "Diyala", "Ninewa"]
        else:
            defaults = ["Erbil", "Slemani", "Duhok"]

        for g in defaults:
            Governorate.objects.get_or_create(election=e, name=g)

        messages.success(request, "Election created.")
        return redirect("election_list")   # 🔥 FIXED HERE

    return render(request, "core/election_create.html")




@login_required
def election_delete(request, pk):
    election = get_object_or_404(Election, pk=pk)

    if request.method == "POST":
        election.delete()
        messages.success(request, "Election deleted successfully.")
        return redirect("election_list")

    return render(request, "core/election_delete.html", {
        "election": election
    })



@login_required
def election_update(request, pk):
    election = get_object_or_404(Election, pk=pk)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        election_type = request.POST.get("election_type", "")
        status = request.POST.get("status", "")
        election_date = request.POST.get("election_date") or None

        if not name:
            messages.error(request, "Election name is required.")
            return redirect("election_update", pk=pk)

        if election_type not in ["IRAQ", "KRG"]:
            messages.error(request, "Invalid election type.")
            return redirect("election_update", pk=pk)

        if status not in ["ACTIVE", "FINISHED"]:
            messages.error(request, "Invalid status.")
            return redirect("election_update", pk=pk)

        election.name = name
        election.election_type = election_type
        election.status = status
        election.election_date = election_date
        election.save()

        messages.success(request, "Election updated successfully.")
        return redirect("election_list")

    return render(request, "core/election_update.html", {
        "election": election
    })


@login_required
def election_detail(request, pk):   # keep pk

    election = get_object_or_404(Election, id=pk)

    # 🔥 THIS IS THE FIX
    govs = election.governorates.all().order_by("name")

    for g in govs:

        public_total = (
            VoteRecord.objects.filter(
                election=election,
                governorate=g,
                voting_type__iexact="Public"
            ).aggregate(total=Sum("number_of_votes"))["total"] or 0
        )

        special_total = (
            VoteRecord.objects.filter(
                election=election,
                governorate=g,
                voting_type__iexact="Special"
            ).aggregate(total=Sum("number_of_votes"))["total"] or 0
        )

        g.public_total = public_total
        g.special_total = special_total
        g.total_votes = public_total + special_total

    return render(request, "core/election_detail.html", {
        "election": election,
        "govs": govs,
    })


from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

@login_required
def governorate_detail(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    districts = governorate.districts.order_by("name")

    # Public Votes (PUK)
    public_total = (
        VoteRecord.objects.filter(
            election=election,
            governorate=governorate,
            voting_type__iexact="Public"
        )
        .aggregate(total=Coalesce(Sum("number_of_votes"), 0))["total"]
    )

    # Special Votes (PUK)
    special_total = (
        VoteRecord.objects.filter(
            election=election,
            governorate=governorate,
            voting_type__iexact="Special"
        )
        .aggregate(total=Coalesce(Sum("number_of_votes"), 0))["total"]
    )

    total_votes = public_total + special_total

    # ✅ Total Allowed Votes (from ElectionUnit, loaded via GEO)
    total_allowed_votes = (
        ElectionUnit.objects.filter(
            election=election,
            governorate=governorate
        )
        .aggregate(total=Coalesce(Sum("total_allowed_votes"), 0))["total"]
    )

    # ✅ Public % only (PUK Public / Total Allowed)
    public_percentage = 0
    if total_allowed_votes > 0:
        public_percentage = round((public_total / total_allowed_votes) * 100, 2)

    return render(request, "core/governorate_detail.html", {
        "election": election,
        "governorate": governorate,
        "districts": districts,

        "public_total": public_total,
        "special_total": special_total,
        "total_votes": total_votes,

        "total_allowed_votes": total_allowed_votes,
        "public_percentage": public_percentage,
    })




from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, render


@login_required
def district_detail(request, district_id):
    
    district = get_object_or_404(District, id=district_id)

    voting_type = request.GET.get("type", "Public")

    subdistricts = district.subdistricts.all().order_by("name")

    result = []
    total_puk_votes = 0
    total_allowed_votes = 0

    for sub in subdistricts:

        # 🎯 TOTAL PUK votes in this subdistrict
        puk_votes = VoteRecord.objects.filter(
            election_unit__subdistrict=sub,
            voting_type=voting_type
        ).aggregate(total=Sum("number_of_votes"))["total"] or 0

        # 🎯 TOTAL Allowed Votes from Units in this subdistrict
        allowed_votes = ElectionUnit.objects.filter(
            subdistrict=sub
        ).aggregate(total=Sum("total_allowed_votes"))["total"] or 0

        # 🎯 percentage
        if allowed_votes > 0:
            percent = (puk_votes / allowed_votes) * 100
        else:
            percent = 0

        total_puk_votes += puk_votes
        total_allowed_votes += allowed_votes

        result.append({
            "sub": sub,
            "puk_votes": puk_votes,
            "allowed_votes": allowed_votes,
            "percent": percent
        })

    # 🔥 overall percent
    if total_allowed_votes > 0:
        overall_percent = (total_puk_votes / total_allowed_votes) * 100
    else:
        overall_percent = 0

    return render(request, "core/district_detail.html", {
        "district": district,
        "subdistricts_data": result,
        "voting_type": voting_type,
        "total_puk_votes": total_puk_votes,
        "total_allowed_votes": total_allowed_votes,
        "overall_percent": overall_percent,
    })



from django.db.models import Sum, Q

@login_required
def subdistrict_detail(request, subdistrict_id):
    subdistrict = get_object_or_404(SubDistrict, id=subdistrict_id)

    voting_type = request.GET.get("type", "Public")
    search_query = request.GET.get("q", "").strip()

    units = (
        ElectionUnit.objects
        .filter(subdistrict=subdistrict)
        .annotate(
            total_votes=Sum(
                "vote_records__number_of_votes",
                filter=Q(
                    vote_records__voting_type__iexact=voting_type
                )
            )
        )
    )

    # ✅ SEARCH FILTER
    if search_query:
        units = units.filter(
            Q(election_unit_number__icontains=search_query) |
            Q(election_unit_name__icontains=search_query) |
            Q(election_unit_address__icontains=search_query)
        )

    units = units.order_by("election_unit_number")

    # Totals
    total_puk_votes = sum(u.total_votes or 0 for u in units)
    total_allowed_votes = sum(u.total_allowed_votes or 0 for u in units)

    puk_percentage = 0
    if total_allowed_votes > 0:
        puk_percentage = (total_puk_votes / total_allowed_votes) * 100

    return render(request, "core/subdistrict_detail.html", {
        "subdistrict": subdistrict,
        "units": units,
        "voting_type": voting_type,
        "total_puk_votes": total_puk_votes,
        "total_allowed_votes": total_allowed_votes,
        "puk_percentage": puk_percentage,
        "search_query": search_query,
    })

from django.db.models import Sum
from django.db.models.functions import Upper

@login_required
def unit_detail(request, unit_id):
    unit = get_object_or_404(ElectionUnit, id=unit_id)

    vote_type = request.GET.get("type", "Public").capitalize()

    # 🔥 Important: force case-insensitive match
    votes_queryset = VoteRecord.objects.filter(
        election_unit=unit,
        voting_type__iexact=vote_type
    )

    # Total votes
    total_votes = (
        votes_queryset
        .aggregate(total=Sum("number_of_votes"))["total"] or 0
    )

    # Totals by list
    per_list = (
        votes_queryset
        .values("list_number", "list_name")
        .annotate(total=Sum("number_of_votes"))
        .order_by("-total")
    )

    # Top candidates
    top_candidates = (
        votes_queryset
        .values("candidate_number", "candidate_name", "list_name")
        .annotate(total=Sum("number_of_votes"))
        .order_by("-total")
    )

    return render(request, "core/unit_detail.html", {
        "unit": unit,
        "total_votes": total_votes,
        "per_list": per_list,
        "top_candidates": top_candidates,
        "vote_type": vote_type,
    })
# ---------- uploads ----------
@login_required
def upload_geo(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    if request.method == "POST":
        f = request.FILES.get("file")
        if not f:
            messages.error(request, "Please choose a GEO Excel file.")
            return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

        try:
            df = clean_dataframe(pd.read_excel(f))
        except Exception as ex:
            messages.error(request, f"Cannot read GEO Excel: {ex}")
            return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

        # ✅ REQUIRED COLUMNS (UPDATED)
        required_geo = [
            "Governorate",
            "District",
            "Subdistrict",
            "Election Unit Number",
            "Election Unit Name",
            "Election Unit Address",
            "Total Allowed Votes",
        ]

        missing = [c for c in required_geo if c not in df.columns]
        if missing:
            messages.error(request, "GEO file missing columns: " + ", ".join(missing))
            return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

        created_units = 0
        created_districts = 0
        created_subdistricts = 0
        skipped = 0

        with transaction.atomic():

            for _, row in df.iterrows():

                raw_unit = row.get("Election Unit Number")

                if pd.isna(raw_unit):
                    skipped += 1
                    continue

                try:
                    unit_no = str(int(float(raw_unit)))
                except Exception:
                    skipped += 1
                    continue

                # ---------------- SAFE TEXT FIELDS ----------------
                d_name = safe_str(row.get("District")) or "Unknown"
                s_name = safe_str(row.get("Subdistrict")) or "Unknown"

                # ---------------- ALLOWED VOTES ----------------
                raw_allowed = row.get("Total Allowed Votes")
                try:
                    allowed_votes = int(float(raw_allowed)) if not pd.isna(raw_allowed) else 0
                except Exception:
                    allowed_votes = 0

                # ---------------- CREATE DISTRICT ----------------
                district, d_created = District.objects.get_or_create(
                    governorate=governorate,
                    name=d_name
                )

                # ---------------- CREATE SUBDISTRICT ----------------
                subdistrict, s_created = SubDistrict.objects.get_or_create(
                    district=district,
                    name=s_name
                )

                if d_created:
                    created_districts += 1
                if s_created:
                    created_subdistricts += 1

                # ---------------- CREATE OR UPDATE UNIT ----------------
                unit, created = ElectionUnit.objects.get_or_create(
                    election=election,
                    election_unit_number=unit_no,
                    defaults={
                        "governorate": governorate,
                        "district": district,
                        "subdistrict": subdistrict,
                        "election_unit_name": safe_str(row.get("Election Unit Name")),
                        "election_unit_address": safe_str(row.get("Election Unit Address")),
                        "total_allowed_votes": allowed_votes,
                    }
                )

                # ✅ ALWAYS UPDATE (SAFE)
                unit.governorate = governorate
                unit.district = district
                unit.subdistrict = subdistrict
                unit.election_unit_name = safe_str(row.get("Election Unit Name"))
                unit.election_unit_address = safe_str(row.get("Election Unit Address"))
                unit.total_allowed_votes = allowed_votes
                unit.save()

                if created:
                    created_units += 1

        messages.success(
            request,
            f"GEO imported successfully. Districts +{created_districts}, "
            f"Subdistricts +{created_subdistricts}, "
            f"Units +{created_units}. Skipped rows: {skipped}."
        )

        return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

    return render(request, "core/upload_geo.html", {
        "election": election,
        "governorate": governorate
    })


from django.db import transaction
from django.db.models import Sum
import pandas as pd




@login_required
def upload_votes(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    vote_type = request.GET.get("type", "Public").capitalize()

    if request.method == "POST":
        f = request.FILES.get("file")
        if not f:
            messages.error(request, "Please choose a VOTING Excel file.")
            return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

        try:
            df = clean_dataframe(pd.read_excel(f))
        except Exception as ex:
            messages.error(request, f"Cannot read VOTING Excel: {ex}")
            return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

        required_votes = [
            "Election Unit Number",
            "Number of Votes",
            "Candidate number",
            "Candidate name",
            "List Name",
            "List Number",
        ]

        missing = [c for c in required_votes if c not in df.columns]
        if missing:
            messages.error(request, "VOTING file missing columns: " + ", ".join(missing))
            return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

        inserted = 0
        skipped = 0

        with transaction.atomic():

            # Remove previous votes of same type
            VoteRecord.objects.filter(
                election=election,
                governorate=governorate,
                voting_type=vote_type
            ).delete()

            for _, row in df.iterrows():

                raw_unit = row.get("Election Unit Number")

                if pd.isna(raw_unit):
                    skipped += 1
                    continue

                try:
                    unit_no = str(int(float(raw_unit)))
                except Exception:
                    skipped += 1
                    continue

                # 🔵 SPECIAL: no geo needed
                if vote_type == "Special":
                    unit = ElectionUnit.objects.filter(
                        election=election,
                        election_unit_number=unit_no
                    ).first()

                    if not unit:
                        # Create unit automatically for special
                        unit = ElectionUnit.objects.create(
                            election=election,
                            governorate=governorate,
                            election_unit_number=unit_no,
                            election_unit_name=str(row.get("Election Unit Name", "")).strip(),
                            election_unit_address=str(row.get("Election Unit Address", "")).strip(),
                        )

                # 🟢 PUBLIC: must exist in geo
                else:
                    unit = ElectionUnit.objects.filter(
                        election=election,
                        election_unit_number=unit_no
                    ).first()

                    if not unit:
                        skipped += 1
                        continue

                VoteRecord.objects.create(
                    election=election,
                    governorate=governorate,
                    election_unit=unit,
                    candidate_number=str(row.get("Candidate number", "")).strip(),
                    candidate_name=str(row.get("Candidate name", "")).strip(),
                    list_name=str(row.get("List Name", "")).strip(),
                    list_number=str(row.get("List Number", "")).strip(),
                    gender=str(row.get("Gender", "")).strip(),
                    voting_type=vote_type,
                    voting_governorate=str(row.get("Voting Governorate", "")).strip(),
                    station_number=str(row.get("Station Number", "")).strip(),
                    number_of_votes=int(float(row.get("Number of Votes", 0))),
                )

                inserted += 1

        messages.success(
            request,
            f"{vote_type} votes imported: {inserted} rows. Skipped: {skipped}."
        )

        return redirect("governorate_detail", election_id=election.id, gov_id=governorate.id)

    return render(request, "core/upload_votes.html", {
        "election": election,
        "governorate": governorate,
        "vote_type": vote_type,
    })
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

@login_required
def governorate_public(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    search = request.GET.get("search", "").strip()

    districts = governorate.districts.all()

    if search:
        districts = districts.filter(name__icontains=search)

    data = []
    total_puk = 0
    total_allowed = 0

    for d in districts:

        units = ElectionUnit.objects.filter(district=d)

        puk_votes = VoteRecord.objects.filter(
            election=election,
            governorate=governorate,
            voting_type="Public",
            election_unit__in=units
        ).aggregate(total=Coalesce(Sum("number_of_votes"), 0))["total"]

        allowed_votes = units.aggregate(
            total=Coalesce(Sum("total_allowed_votes"), 0)
        )["total"]

        percentage = 0
        if allowed_votes > 0:
            percentage = round((puk_votes / allowed_votes) * 100, 2)

        total_puk += puk_votes
        total_allowed += allowed_votes

        data.append({
            "district": d,
            "puk_votes": puk_votes,
            "allowed_votes": allowed_votes,
            "percentage": percentage,
        })

    overall_percentage = 0
    if total_allowed > 0:
        overall_percentage = round((total_puk / total_allowed) * 100, 2)

    return render(request, "core/governorate_public.html", {
        "election": election,
        "governorate": governorate,
        "district_data": data,
        "total_puk": total_puk,
        "total_allowed": total_allowed,
        "overall_percentage": overall_percentage,
        "search_query": search,
    })

from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

@login_required
def governorate_special(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    search = request.GET.get("search", "").strip()

    # 🎯 Start from VoteRecord instead of ElectionUnit
    vote_queryset = VoteRecord.objects.filter(
        election=election,
        governorate=governorate,
        voting_type__iexact="Special"
    )

    if search:
        vote_queryset = vote_queryset.filter(
            Q(election_unit__election_unit_name__icontains=search) |
            Q(election_unit__election_unit_number__icontains=search)
        )

    # 🔥 SINGLE AGGREGATION QUERY
    aggregated = (
        vote_queryset
        .values(
            "election_unit",
            "election_unit__election_unit_number",
            "election_unit__election_unit_name",
            "election_unit__election_unit_address",
            "voting_governorate",
        )
        .annotate(total_votes=Coalesce(Sum("number_of_votes"), 0))
        .order_by("-total_votes")
    )

    total_votes = aggregated.aggregate(
        grand_total=Coalesce(Sum("total_votes"), 0)
    )["grand_total"]

    return render(request, "core/governorate_special.html", {
        "election": election,
        "governorate": governorate,
        "unit_data": aggregated,
        "total_votes": total_votes,
        "search": search,
    })





@login_required
def special_unit_detail(request, election_id, unit_id):
    election = get_object_or_404(Election, id=election_id)
    unit = get_object_or_404(ElectionUnit, id=unit_id)

    votes = (
        VoteRecord.objects.filter(
            election=election,
            election_unit=unit,
            voting_type__iexact="Special"
        )
        .values(
            "candidate_number",
            "candidate_name",
            "list_number",
            "list_name",
        )
        .annotate(
            total_votes=Coalesce(Sum("number_of_votes"), 0)
        )
        .order_by("-total_votes")
    )

    total_votes = votes.aggregate(
        total=Coalesce(Sum("total_votes"), 0)
    )["total"]

    return render(request, "core/special_unit_detail.html", {
        "election": election,
        "unit": unit,
        "votes": votes,
        "total_votes": total_votes,
    })
