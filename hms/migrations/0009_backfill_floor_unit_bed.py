# Data migration: backfill Floor / Unit / Bed records for rooms created
# before the hierarchy was introduced. Existing room.floor values are used
# to build the Floor/Unit tree so no data is lost, and each room receives
# one bed per unit of capacity.
from django.db import migrations


def backfill_hierarchy(apps, schema_editor):
    Room = apps.get_model('hms', 'Room')
    Floor = apps.get_model('hms', 'Floor')
    Unit = apps.get_model('hms', 'Unit')
    Bed = apps.get_model('hms', 'Bed')

    for room in Room.objects.all():
        floor = Floor.objects.filter(hostel_id=room.hostel_id, number=room.floor).first()
        if floor is None:
            floor = Floor.objects.create(hostel_id=room.hostel_id, number=room.floor)
        unit = Unit.objects.filter(floor=floor, name='A').first()
        if unit is None:
            unit = Unit.objects.create(floor=floor, name='A')
        room.unit = unit
        room.floor_number = room.floor
        room.save(update_fields=['unit', 'floor_number'])
        existing = Bed.objects.filter(room_id=room.pk).count()
        for i in range(existing + 1, max(room.capacity, 1) + 1):
            Bed.objects.create(room_id=room.pk, bed_number=f'Bed {i}', status='available')


def unbackfill_hierarchy(apps, schema_editor):
    # Best effort reverse: restore the denormalized floor number.
    Room = apps.get_model('hms', 'Room')
    for room in Room.objects.select_related('unit__floor'):
        if room.unit_id:
            room.floor = room.unit.floor.number
            room.save(update_fields=['floor'])


class Migration(migrations.Migration):

    dependencies = [
        ('hms', '0008_roomtype_remove_room_floor_complaint_hostel_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_hierarchy, unbackfill_hierarchy),
    ]
