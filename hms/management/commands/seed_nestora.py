"""
Seed Touch and Solve (TNS) with demo data.

Creates (idempotent — safe to run multiple times):
    - Room types
    - The single "Touch and Solve (TNS) Hostel" with its manager
    - 7 floors x 2 units x 4 rooms x 4 beds (= 56 rooms, 224 beds)
    - Super admin / manager / renter accounts
    - A few bookings, payments, complaints, notices and meal settings

Usage:
    python manage.py seed_nestora [--flush-demo]
"""
from datetime import date, timedelta
from decimal import Decimal
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from hms.models import (
    User, Hostel, RoomType, Floor, Unit, Room, Bed,
    Booking, Payment, Complaint, Notice, MealSettings,
)


class Command(BaseCommand):
    help = 'Seed the database with demo data for Touch and Solve (TNS).'

    def add_arguments(self, parser):
        parser.add_argument('--flush-demo', action='store_true',
                            help='Delete previously seeded demo hostel before seeding.')

    @transaction.atomic
    def handle(self, *args, **options):
        passwords = {
            'admin': os.environ.get('NESTORA_DEMO_ADMIN_PASSWORD'),
            'manager': os.environ.get('NESTORA_DEMO_MANAGER_PASSWORD'),
            'renter': os.environ.get('NESTORA_DEMO_RENTER_PASSWORD'),
        }
        missing_passwords = [
            f'NESTORA_DEMO_{role.upper()}_PASSWORD'
            for role, password in passwords.items()
            if not password
        ]
        if missing_passwords:
            raise CommandError(
                'Set demo account passwords before seeding: '
                + ', '.join(missing_passwords)
            )

        self.stdout.write('Seeding Touch and Solve (TNS) demo data...')

        # ---------- Users ----------
        admin = self._user(
            email='admin@tns-hostel.com', password=passwords['admin'],
            full_name='System Super Admin', role='SUPER_ADMIN', phone='01700000001',
        )
        manager = self._user(
            email='manager@tns-hostel.com', password=passwords['manager'],
                full_name='Touch and Solve (TNS) Hostel Manager', role='HOSTEL_MANAGER', phone='01700000002',
        )
        renters = []
        renter_names = [
            ('Rahim Uddin', 'rahim@student.com'),
            ('Karim Ahmed', 'karim@student.com'),
            ('Sabbir Hossain', 'sabbir@student.com'),
            ('Nayeem Islam', 'nayeem@student.com'),
            ('Tanvir Hasan', 'tanvir@student.com'),
        ]
        for i, (name, email) in enumerate(renter_names, start=1):
            renters.append(self._user(
                email=email, password=passwords['renter'],
                full_name=name, role='RENTER', phone=f'0170000001{i}',
            ))

        # ---------- Room types ----------
        type_specs = [
            ('Standard', 4, 2800, 'Shared room with essential furnishings.'),
            ('Premium', 4, 3500, 'Spacious shared room with premium facilities.'),
            ('Deluxe', 4, 4500, 'Top-floor shared room with AC and balcony.'),
        ]
        room_types = {name: RoomType.objects.get_or_create(
            name=name, defaults={'description': desc})[0]
            for name, cap, price, desc in type_specs}

        # ---------- Hostel ----------
        if options['flush_demo']:
            old = Hostel.objects.filter(slug__in=['nestora-hostel', 'demo-hostel'])
            Booking.objects.filter(room__hostel__in=old).delete()
            Room.objects.filter(hostel__in=old).delete()  # beds cascade; unit is PROTECT
            deleted, _ = old.delete()
            self.stdout.write(f'Removed previous demo hostel data ({deleted} records).')

        hostel, created = Hostel.objects.get_or_create(
            slug='nestora-hostel',
            defaults={
                'name': 'Touch and Solve (TNS) Hostel',
                'city': 'Dhaka',
                'address': '12/A University Road, Dhanmondi, Dhaka',
                'description': (
                    'A modern seven-storey student hostel managed through Touch and Solve (TNS). '
                    'Fully furnished shared rooms, high speed internet, meals and 24/7 security.'
                ),
                'allocation_policy': 'FCFS',
                'confirmation_policy': 'AUTO',
                'contact_phone': '01700000000',
                'contact_email': 'info@tns-hostel.com',
                'facilities': 'WiFi, Mess, Laundry, Common Room, Study Room, CCTV, Generator, Prayer Room',
                'manager': manager,
            },
        )
        if created:
            self.stdout.write(f'Created hostel: {hostel.name}')
        else:
            if not hostel.manager:
                hostel.manager = manager
                hostel.save()
            self.stdout.write(f'Hostel already exists: {hostel.name}')

        # ---------- Structure: 7 floors x 2 units x 4 rooms x 4 beds ----------
        floor_names = {
            0: 'Ground Floor', 1: '1st Floor', 2: '2nd Floor', 3: '3rd Floor',
            4: '4th Floor', 5: '5th Floor', 6: '6th Floor',
        }
        beds_created = rooms_created = 0
        for floor_no in range(0, 7):
            floor, f_created = Floor.objects.get_or_create(
                hostel=hostel, number=floor_no,
                defaults={'name': floor_names[floor_no]},
            )
            if f_created:
                self.stdout.write(f'  {floor_names[floor_no]} created')
            prefix = floor_no + 1  # Ground -> 1xx ... 6th -> 7xx
            for unit_no in range(1, 3):
                unit, _ = Unit.objects.get_or_create(
                    floor=floor,
                    name=chr(64 + unit_no),
                    defaults={'description': f'{floor_names[floor_no]} — Unit {chr(64 + unit_no)}'},
                )
                for room_idx in range(1, 5):
                    room_number = f'{prefix}{(unit_no - 1) * 4 + room_idx:02d}'
                    size = 160 + ((floor_no * 4 + room_idx) % 5) * 15          # 160–220 sq ft
                    rent = Decimal(2600 + floor_no * 120 + (room_idx - 1) * 80)  # rises with floor
                    is_ac = (floor_no >= 4) or (floor_no % 2 == 1)
                    r_type = room_types['Deluxe'] if floor_no == 6 else (
                        room_types['Premium'] if is_ac else room_types['Standard'])
                    room, r_created = Room.objects.get_or_create(
                        hostel=hostel,
                        room_number=room_number,
                        defaults={
                            'unit': unit,
                            'room_type': r_type,
                            'max_occupancy': 4,
                            'size_sqft': size,
                            'is_ac': is_ac,
                            'attached_bathroom': True,
                            'num_bathrooms': 1,
                            'has_balcony': (room_idx in (1, 4)),
                            'rent': rent,
                            'security_deposit': Decimal('2000.00'),
                            'description': (
                                f'Shared room with 4 single beds on the {floor_names[floor_no].lower()}. '
                                f'{"AC" if is_ac else "Non-AC"}, attached bathroom'
                                f'{", balcony" if room_idx in (1, 4) else ""}.'
                            ),
                            'amenities': 'Bed, Mattress, Wardrobe, Study Table, Chair, Reading Light, Fan',
                        },
                    )
                    if r_created:
                        rooms_created += 1
                    for bed_no in range(1, 5):
                        # Assign realistic physical attributes per bed
                        position_map = {1: 'left', 2: 'right', 3: 'left', 4: 'right'}
                        window_side_map = {1: False, 2: True, 3: False, 4: True}
                        window_direction_map = {1: '', 2: 'east', 3: '', 4: 'east'}
                        near_door_map = {1: True, 2: False, 3: False, 4: True}
                        locker_map = {1: f'L-{room_number}-01', 2: f'L-{room_number}-02', 
                                      3: f'L-{room_number}-03', 4: f'L-{room_number}-04'}

                        _, b_created = Bed.objects.get_or_create(
                            room=room,
                            bed_number=f'Bed {bed_no}',
                            defaults={
                                'status': 'available',
                                'position': position_map[bed_no],
                                'window_side': window_side_map[bed_no],
                                'window_direction': window_direction_map[bed_no],
                                'room_side': position_map[bed_no],
                                'near_door': near_door_map[bed_no],
                                'has_charging_point': True,
                                'has_reading_light': True,
                                'locker_number': locker_map[bed_no],
                            },
                        )
                        if b_created:
                            beds_created += 1
                    room.refresh_status()

        totals = (
            Floor.objects.filter(hostel=hostel).count(),
            Unit.objects.filter(floor__hostel=hostel).count(),
            Room.objects.filter(hostel=hostel).count(),
            Bed.objects.filter(room__hostel=hostel).count(),
        )
        self.stdout.write(f'Structure: {totals[0]} floors, {totals[1]} units, {totals[2]} rooms, {totals[3]} beds')
        self.stdout.write(f'New this run — rooms: {rooms_created}, beds: {beds_created}')

        # ---------- Bookings + payments ----------
        today = date.today()
        booking_count = 0
        for i, renter in enumerate(renters[:4]):
            room = Room.objects.filter(hostel=hostel, beds__status='available').distinct().first()
            if not room:
                break
            bed = room.beds.filter(status='available').first()
            check_in = today + timedelta(days=3 + i)
            existing = Booking.objects.filter(user=renter, bed=bed, status__in=['pending', 'confirmed']).exists()
            if existing:
                continue
            booking = Booking.objects.create(
                user=renter,
                room=room,
                bed=bed,
                check_in=check_in,
                check_out=check_in + timedelta(days=180),
                total_amount=room.rent,
                advance_paid=room.rent if i < 3 else Decimal('0.00'),
                payment_status='paid' if i < 3 else 'unpaid',
                status='checked_in' if i == 0 else 'confirmed' if i < 3 else 'pending',
            )
            booking_count += 1
            if i < 3:
                Payment.objects.create(
                    booking=booking,
                    user=renter,
                    transaction_id=f'DEMO-TXN-{booking.booking_reference}',
                    amount=room.rent,
                    currency='BDT',
                    status='success',
                    payment_method='bKash',
                )
            if booking.status == 'checked_in':
                Bed.objects.filter(pk=bed.pk).update(status='occupied')
            room.refresh_status()
        self.stdout.write(f'Demo bookings created: {booking_count}')

        # ---------- Complaints ----------
        complaint_specs = [
            (renters[0], 'Water leakage in bathroom', 'plumbing', 'high'),
            (renters[1], 'WiFi keeps disconnecting at night', 'internet', 'medium'),
        ]
        for renter, subject, category, priority in complaint_specs:
            if not Complaint.objects.filter(user=renter, subject=subject).exists():
                Complaint.objects.create(
                    user=renter,
                    hostel=hostel,
                    subject=subject,
                    description=f'{subject}. Requesting maintenance support.',
                    category=category,
                    priority=priority,
                )
        self.stdout.write('Complaints ensured.')

        # ---------- Notices ----------
        notice_specs = [
            ('Hostel reopens after semester break',
             'All students must check in within 3 days of reopening.', 'general', True),
            ('Mess menu updated',
             'The monthly mess menu has been updated. Check the dining notice board.', 'notice', False),
        ]
        for title, content, category, is_public in notice_specs:
            Notice.objects.get_or_create(
                title=title,
                defaults={
                    'content': content,
                    'category': category,
                    'hostel': None if is_public else hostel,
                    'created_by': manager,
                    'is_active': True,
                },
            )
        self.stdout.write('Notices ensured.')

        # ---------- Meal settings ----------
        ms, _ = MealSettings.objects.get_or_create(
            hostel=hostel,
            defaults={
                'is_enabled': True,
                'rate_breakfast': Decimal('60.00'),
                'rate_lunch': Decimal('100.00'),
                'rate_dinner': Decimal('90.00'),
                'cutoff_hours': 6,
                'default_status': 'on',
            },
        )
        self.stdout.write(f'Meal settings ready (enabled={ms.is_enabled}).')

        self.stdout.write(self.style.SUCCESS('Done.'))
        self.stdout.write('')
        self.stdout.write('Login accounts:')
        self.stdout.write('  Super Admin : admin@tns-hostel.com')
        self.stdout.write('  Manager     : manager@tns-hostel.com')
        self.stdout.write('  Renters     : rahim@student.com, karim@student.com, ...')

    def _user(self, email, password, full_name, role, phone):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'full_name': full_name,
                'role': role,
                'phone': phone,
                'is_staff': role == 'SUPER_ADMIN',
                'is_superuser': False,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        return user
