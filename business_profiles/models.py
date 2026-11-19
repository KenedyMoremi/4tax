from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class SectorProfile(models.Model):
    class Sector(models.TextChoices):
        TRANSPORT = 'transport', 'Transport'
        SERVICES = 'services', 'Services'
        ECOMMERCE = 'ecommerce', 'E-Commerce'
        RETAIL = 'retail', 'Retail'
        AGRICULTURE = 'agriculture', 'Agriculture'

    business = models.OneToOneField('books.Business', on_delete=models.CASCADE, related_name='sector_profile')
    sector = models.CharField(max_length=20, choices=Sector.choices)
    owner_id_number = models.CharField('Owner’s national ID number', max_length=40)
    # Sector-specific registration data is validated by typed Django forms before saving.
    # Monetary values are serialized as decimal strings, never binary floats.
    details = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(sector__in=['transport','services','ecommerce','retail','agriculture']), name='valid_profile_sector')]
