from django.db import models
from django.core.validators import MinValueValidator


from django.db import models

class Election(models.Model):
    TYPE_IRAQ = "IRAQ"
    TYPE_KRG = "KRG"
    TYPE_CHOICES = [
        (TYPE_IRAQ, "Iraq"),
        (TYPE_KRG, "Kurdistan")
    ]

    STATUS_ACTIVE = "ACTIVE"
    STATUS_FINISHED = "FINISHED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_FINISHED, "Finished")
    ]

    name = models.CharField(max_length=200)

    election_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE
    )

    election_date = models.DateField(
        null=False,
        blank=False
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["election_date", "election_type"],
                name="unique_date_per_type"
            )
        ]

    def __str__(self):
        return self.name


class Governorate(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="governorates")
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ("election", "name")

    def __str__(self):
        return self.name


class District(models.Model):
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE, related_name="districts")
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = ("governorate", "name")

    def __str__(self):
        return self.name


class SubDistrict(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="subdistricts")
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = ("district", "name")

    def __str__(self):
        return self.name


class ElectionUnit(models.Model):
    # Join key with both Excel files (exact header name: "Election Unit Number")
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="units")
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE, related_name="units")
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name="units")
    subdistrict = models.ForeignKey(SubDistrict, on_delete=models.SET_NULL, null=True, blank=True, related_name="units")

    election_unit_number = models.CharField(max_length=50)  # store as str always
    election_unit_name = models.CharField(max_length=250, blank=True, default="")
    election_unit_address = models.CharField(max_length=300, blank=True, default="")

    stations_count = models.PositiveIntegerField(default=0)
# ✅ NEW FIELD
    total_allowed_votes = models.PositiveIntegerField(default=0)
    class Meta:
        unique_together = ("election", "election_unit_number")
        indexes = [
            models.Index(fields=["election", "election_unit_number"]),
            models.Index(fields=["governorate"]),
            models.Index(fields=["district"]),
            models.Index(fields=["subdistrict"]),
        ]

    def __str__(self):
        return f"{self.election_unit_number} - {self.election_unit_name}"


class VoteRecord(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="votes")
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE, related_name="votes")
    election_unit = models.ForeignKey(ElectionUnit, on_delete=models.CASCADE, related_name="vote_records")

    # EXACT voting headers (sulyvotes.xlsx)
    candidate_number = models.CharField(max_length=50)
    candidate_name = models.CharField(max_length=250)

    list_name = models.CharField(max_length=250)
    list_number = models.CharField(max_length=50)

    gender = models.CharField(max_length=20, blank=True, default="")
    voting_type = models.CharField(max_length=50)  # Public / Special
    voting_governorate = models.CharField(max_length=100, blank=True, default="")

    station_number = models.CharField(max_length=50, blank=True, default="")
    number_of_votes = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["election", "governorate"]),
            models.Index(fields=["election_unit"]),
            models.Index(fields=["list_number"]),
            models.Index(fields=["voting_type"]),
        ]

        


class VoteUploadLog(models.Model):

    election = models.ForeignKey(Election, on_delete=models.CASCADE)
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE)

    filename = models.CharField(max_length=255)

    inserted_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.election.name} - {self.governorate.name} - {self.uploaded_at}"
