from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from datetime import date
from .models import Election, Governorate

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
from django.core.paginator import Paginator

@login_required
def election_list(request):
    elections = Election.objects.order_by("-id")

    paginator = Paginator(elections, 9)  # 3 rows × 3 columns
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "core/election_list.html", {
        "elections": page_obj
    })





@login_required
def election_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        election_type = (request.POST.get("election_type") or "").strip()
        status = (request.POST.get("status") or "ACTIVE").strip()
        election_date = (request.POST.get("election_date") or "").strip()

        # 🔹 Name Required
        if not name:
            messages.error(request, "Election name is required.")
            return redirect("election_create")

        # 🔹 Date Required
        if not election_date:
            messages.error(request, "Election date is required.")
            return redirect("election_create")

        # 🔹 Validate Date Format
        try:
            election_date_obj = date.fromisoformat(election_date)
        except Exception:
            messages.error(request, "Invalid election date.")
            return redirect("election_create")

        # 🔹 Prevent Future Date
        if election_date_obj > date.today():
            messages.error(request, "Election date cannot be in the future.")
            return redirect("election_create")

        # 🔹 Validate Election Type
        if election_type not in [Election.TYPE_IRAQ, Election.TYPE_KRG]:
            messages.error(request, "Invalid election type.")
            return redirect("election_create")

        # 🔹 Validate Status
        if status not in [Election.STATUS_ACTIVE, Election.STATUS_FINISHED]:
            messages.error(request, "Invalid status.")
            return redirect("election_create")

        # 🔹 Prevent Same Type + Same Date
        if Election.objects.filter(
            election_date=election_date_obj,
            election_type=election_type
        ).exists():
            messages.error(request, "An election of this type already exists on this date.")
            return redirect("election_create")

        # ✅ Create Election
        e = Election.objects.create(
            name=name,
            election_type=election_type,
            status=status,
            election_date=election_date_obj,
        )

        # 🔹 Create Default Governorates
        if election_type == Election.TYPE_IRAQ:
            defaults = ["Slemani", "Erbil", "Duhok", "Kirkuk", "Diyala", "Ninewa"]
        else:
            defaults = ["Erbil", "Slemani", "Duhok"]

        for g in defaults:
            Governorate.objects.get_or_create(election=e, name=g)

        messages.success(request, "Election created successfully.")
        return redirect("election_list")

    return render(request, "core/election_create.html")


from django.shortcuts import get_object_or_404


@login_required
def election_delete(request, pk):
    election = get_object_or_404(Election, pk=pk)

    # 🔒 Block Deleting Finished Election
    if election.status == Election.STATUS_FINISHED:
        messages.error(request, "Finished elections cannot be deleted.")
        return redirect("election_list")

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
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

@login_required
def governorate_detail(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    # =========================
    # PARTY HANDLING (SAFE)
    # =========================
    selected_party = request.GET.get("party")

    if not selected_party or selected_party == "":
        selected_party = "all"

    votes_qs = VoteRecord.objects.filter(
        election=election,
        governorate=governorate
    )

    if selected_party != "all":
        votes_qs = votes_qs.filter(list_number=selected_party)

    # =========================
    # CALCULATIONS
    # =========================
    total_votes = votes_qs.aggregate(
        total=Coalesce(Sum("number_of_votes"), 0)
    )["total"]

    public_total = votes_qs.filter(
        voting_type__iexact="Public"
    ).aggregate(
        total=Coalesce(Sum("number_of_votes"), 0)
    )["total"]

    special_total = votes_qs.filter(
        voting_type__iexact="Special"
    ).aggregate(
        total=Coalesce(Sum("number_of_votes"), 0)
    )["total"]

    total_allowed_votes = ElectionUnit.objects.filter(
        election=election,
        governorate=governorate
    ).aggregate(
        total=Coalesce(Sum("total_allowed_votes"), 0)
    )["total"]

    public_percentage = 0
    if total_allowed_votes > 0:
        public_percentage = round(
            (public_total / total_allowed_votes) * 100, 2
        )

    # =========================
    # PARTIES DROPDOWN
    # =========================
    parties = VoteRecord.objects.filter(
        election=election,
        governorate=governorate
    ).values("list_number", "list_name").distinct().order_by("list_number")

    return render(request, "core/governorate_detail.html", {
        "election": election,
        "governorate": governorate,
        "total_votes": total_votes,
        "public_total": public_total,
        "special_total": special_total,
        "total_allowed_votes": total_allowed_votes,
        "public_percentage": public_percentage,
        "parties": parties,
        "selected_party": selected_party,
    })

from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

@login_required
def district_detail(request, district_id):

    district = get_object_or_404(District, id=district_id)

    voting_type = request.GET.get("type", "Public")
    party_id = request.GET.get("party", "all")

    subdistricts = district.subdistricts.all().order_by("name")

    result = []
    total_votes = 0
    total_allowed_votes = 0

    for sub in subdistricts:

        votes_qs = VoteRecord.objects.filter(
            election_unit__subdistrict=sub,
            voting_type__iexact=voting_type
        )

        if party_id != "all":
            votes_qs = votes_qs.filter(list_number=party_id)

        votes = votes_qs.aggregate(
            total=Coalesce(Sum("number_of_votes"), 0)
        )["total"]

        allowed_votes = ElectionUnit.objects.filter(
            subdistrict=sub
        ).aggregate(
            total=Coalesce(Sum("total_allowed_votes"), 0)
        )["total"]

        percent = 0
        if allowed_votes > 0:
            percent = round((votes / allowed_votes) * 100, 2)

        total_votes += votes
        total_allowed_votes += allowed_votes

        result.append({
            "sub": sub,
            "votes": votes,
            "allowed_votes": allowed_votes,
            "percent": percent
        })

    overall_percent = 0
    if total_allowed_votes > 0:
        overall_percent = round(
            (total_votes / total_allowed_votes) * 100, 2
        )

    return render(request, "core/district_detail.html", {
        "district": district,
        "subdistricts_data": result,
        "voting_type": voting_type,
        "party_id": party_id,
        "total_votes": total_votes,
        "total_allowed_votes": total_allowed_votes,
        "overall_percent": overall_percent,
    })

@login_required
def subdistrict_detail(request, subdistrict_id):

    subdistrict = get_object_or_404(SubDistrict, id=subdistrict_id)

    voting_type = request.GET.get("type", "Public")
    party_id = request.GET.get("party", "all")
    search_query = request.GET.get("q", "").strip()

    vote_queryset = VoteRecord.objects.filter(
        election=subdistrict.district.governorate.election,
        governorate=subdistrict.district.governorate,
        voting_type__iexact=voting_type,
    )

    if party_id != "all":
        vote_queryset = vote_queryset.filter(list_number=party_id)

    units = ElectionUnit.objects.filter(subdistrict=subdistrict)

    if search_query:
        units = units.filter(
            Q(election_unit_number__icontains=search_query) |
            Q(election_unit_name__icontains=search_query) |
            Q(election_unit_address__icontains=search_query)
        )

    units = units.order_by("election_unit_number")

    for u in units:
        u.total_votes = vote_queryset.filter(
            election_unit=u
        ).aggregate(
            total=Coalesce(Sum("number_of_votes"), 0)
        )["total"]

    total_votes = sum(u.total_votes for u in units)
    total_allowed_votes = sum(u.total_allowed_votes for u in units)

    percentage = 0
    if total_allowed_votes > 0:
        percentage = round((total_votes / total_allowed_votes) * 100, 2)

    return render(request, "core/subdistrict_detail.html", {
        "subdistrict": subdistrict,
        "units": units,
        "voting_type": voting_type,
        "party_id": party_id,
        "total_votes": total_votes,
        "total_allowed_votes": total_allowed_votes,
        "puk_percentage": percentage,
        "search_query": search_query,
    })



@login_required
def unit_detail(request, unit_id):
    unit = get_object_or_404(ElectionUnit, id=unit_id)

    vote_type = request.GET.get("type", "Public")
    party_id = request.GET.get("party", "all")

    votes_queryset = VoteRecord.objects.filter(
        election_unit=unit,
        voting_type__iexact=vote_type
    )

    if party_id != "all":
        votes_queryset = votes_queryset.filter(list_number=party_id)

    total_votes = votes_queryset.aggregate(
        total=Coalesce(Sum("number_of_votes"), 0)
    )["total"]

    per_list = votes_queryset.values(
        "list_number", "list_name"
    ).annotate(
        total=Sum("number_of_votes")
    ).order_by("-total")

    top_candidates = votes_queryset.values(
        "candidate_number",
        "candidate_name",
        "list_name",
    ).annotate(
        total=Sum("number_of_votes")
    ).order_by("-total")

    return render(request, "core/unit_detail.html", {
        "unit": unit,
        "total_votes": total_votes,
        "per_list": per_list,
        "top_candidates": top_candidates,
        "vote_type": vote_type,
        "party_id": party_id,
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
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
import pandas as pd

from .models import Election, Governorate, ElectionUnit, VoteRecord


@login_required
def upload_votes(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    inserted = 0
    skipped = 0
    errors = []

    if request.method == "POST":

        file = request.FILES.get("file")
        if not file:
            messages.error(request, "Please choose a voting Excel file.")
            return redirect("upload_votes", election_id=election.id, gov_id=governorate.id)

        try:
            df = pd.read_excel(file)
        except Exception as e:
            messages.error(request, f"Cannot read Excel file: {e}")
            return redirect("upload_votes", election_id=election.id, gov_id=governorate.id)

        # Clean column names
        df.columns = (
            df.columns
              .str.strip()
              .str.replace(r"\s+", "_", regex=True)
              .str.replace(r"[^\w_]", "", regex=True)
              .str.lower()
        )

        required_columns = [
            "election_unit_number",
            "candidate_number",
            "candidate_name",
            "list_name",
            "list_number",
            "gender",
            "voting_type",
            "voting_governorate",
            "station_number",
            "number_of_votes",
        ]

        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            messages.error(request, "Missing columns: " + ", ".join(missing))
            return redirect("upload_votes", election_id=election.id, gov_id=governorate.id)

        with transaction.atomic():

            units_map = {
                u.election_unit_number: u
                for u in ElectionUnit.objects.filter(
                    election=election,
                    governorate=governorate
                )
            }

            to_create = []

            for row in df.to_dict("records"):

                try:
                    unit_no = str(row.get("election_unit_number")).strip()
                    if not unit_no:
                        skipped += 1
                        continue
                except:
                    skipped += 1
                    continue

                unit = units_map.get(unit_no)
                if not unit:
                    # auto-create unit if missing
                    unit = ElectionUnit.objects.create(
                        election=election,
                        governorate=governorate,
                        election_unit_number=unit_no,
                        election_unit_name=str(row.get("election_unit_name", "")).strip(),
                        election_unit_address=str(row.get("election_unit_address", "")).strip(),
                    )
                    units_map[unit_no] = unit

                try:
                    votes = int(float(row.get("number_of_votes", 0)))
                except:
                    skipped += 1
                    continue

                to_create.append(
                    VoteRecord(
                        election=election,
                        governorate=governorate,
                        election_unit=unit,
                        candidate_number=str(row.get("candidate_number", "")).strip(),
                        candidate_name=str(row.get("candidate_name", "")).strip(),
                        list_name=str(row.get("list_name", "")).strip(),
                        list_number=str(row.get("list_number", "")).strip(),
                        gender=str(row.get("gender", "")).strip(),
                        voting_type=str(row.get("voting_type", "")).strip().capitalize(),
                        voting_governorate=str(row.get("voting_governorate", "")).strip(),
                        station_number=str(row.get("station_number", "")).strip(),
                        number_of_votes=votes,
                    )
                )

            if to_create:
                VoteRecord.objects.bulk_create(to_create, batch_size=5000)
                inserted = len(to_create)

        return render(request, "core/upload_votes.html", {
            "election": election,
            "governorate": governorate,
            "inserted": inserted,
            "updated": 0,
            "skipped": skipped,
            "errors": errors,
            "report": True,
        })

    return render(request, "core/upload_votes.html", {
        "election": election,
        "governorate": governorate,
    })

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

from .models import Election, Governorate, District, ElectionUnit, VoteRecord


@login_required
def governorate_public(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    # -----------------------------
    # PARTY (persist in session)
    # -----------------------------
    session_key = f"selected_party_gov_{gov_id}"

    party_param = request.GET.get("party")
    if party_param is not None and party_param != "":
        selected_party = party_param
        request.session[session_key] = selected_party
    else:
        selected_party = request.session.get(session_key, "all")

    if not selected_party:
        selected_party = "all"

    # -----------------------------
    # SEARCH
    # -----------------------------
    search = request.GET.get("search", "").strip()

    districts = governorate.districts.all().order_by("name")
    if search:
        districts = districts.filter(name__icontains=search)

    data = []
    total_votes = 0
    total_allowed = 0

    # IMPORTANT:
    # show ALL districts even if votes=0 (so the table never becomes empty)
    for d in districts:
        units = ElectionUnit.objects.filter(
            election=election,
            governorate=governorate,
            district=d
        )

        vote_qs = VoteRecord.objects.filter(
            election=election,
            governorate=governorate,
            voting_type__iexact="Public",
            election_unit__in=units
        )

        if selected_party != "all":
            vote_qs = vote_qs.filter(list_number=str(selected_party).strip())

        votes = vote_qs.aggregate(
            total=Coalesce(Sum("number_of_votes"), 0)
        )["total"]

        allowed_votes = units.aggregate(
            total=Coalesce(Sum("total_allowed_votes"), 0)
        )["total"]

        percentage = 0
        if allowed_votes > 0:
            percentage = round((votes / allowed_votes) * 100, 2)

        total_votes += votes
        total_allowed += allowed_votes

        data.append({
            "district": d,
            "votes": votes,
            "allowed_votes": allowed_votes,   # ✅ match template key
            "percentage": percentage,
        })

    overall_percentage = 0
    if total_allowed > 0:
        overall_percentage = round((total_votes / total_allowed) * 100, 2)

    return render(request, "core/governorate_public.html", {
        "election": election,
        "governorate": governorate,
        "district_data": data,
        "total_votes": total_votes,
        "total_allowed": total_allowed,
        "overall_percentage": overall_percentage,
        "selected_party": selected_party,
        "search_query": search,
    })


@login_required
def governorate_special(request, election_id, gov_id):
    election = get_object_or_404(Election, id=election_id)
    governorate = get_object_or_404(Governorate, id=gov_id, election=election)

    search = request.GET.get("search", "").strip()
    selected_party = request.GET.get("party", "all")

    vote_queryset = VoteRecord.objects.filter(
        election=election,
        governorate=governorate,
        voting_type__iexact="Special"
    )

    # 🔥 Party filter
    if selected_party != "all":
        vote_queryset = vote_queryset.filter(list_number=selected_party)

    # 🔍 Search filter
    if search:
        vote_queryset = vote_queryset.filter(
            Q(election_unit__election_unit_name__icontains=search) |
            Q(election_unit__election_unit_number__icontains=search)
        )

    # 🔥 IMPORTANT FIX: group by unit
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

    total_votes = vote_queryset.aggregate(
        total=Coalesce(Sum("number_of_votes"), 0)
    )["total"]

    return render(request, "core/governorate_special.html", {
        "election": election,
        "governorate": governorate,
        "unit_data": aggregated,
        "total_votes": total_votes,
        "search": search,
        "selected_party": selected_party,
    })

@login_required
def special_unit_detail(request, election_id, unit_id):
    election = get_object_or_404(Election, id=election_id)
    unit = get_object_or_404(ElectionUnit, id=unit_id)

    selected_party = request.GET.get("party", "all")

    votes_queryset = VoteRecord.objects.filter(
        election=election,
        election_unit=unit,
        voting_type__iexact="Special"
    )

    # 🔥 Party filter inside unit
    if selected_party != "all":
        votes_queryset = votes_queryset.filter(list_number=selected_party)

    votes = (
        votes_queryset
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

    total_votes = votes_queryset.aggregate(
        total=Coalesce(Sum("number_of_votes"), 0)
    )["total"]

    return render(request, "core/special_unit_detail.html", {
        "election": election,
        "unit": unit,
        "votes": votes,
        "total_votes": total_votes,
        "selected_party": selected_party,
    })


@login_required
def election_data_management(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    governorates = election.governorates.all().order_by("name")

    return render(request, "core/election_data_management.html", {
        "election": election,
        "governorates": governorates,
    })
