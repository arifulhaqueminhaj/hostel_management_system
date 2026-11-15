from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal
import uuid
from datetime import datetime


class UserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPER_ADMIN')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, full_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Admin'),
        ('HOSTEL_MANAGER', 'Hostel Manager'),
        ('RENTER', 'Renter'),
    ]
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='RENTER')
    photo = models.ImageField(upload_to='profiles/', blank=True, null=True)
    address = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    def __str__(self):
        return self.full_name or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        parts = self.full_name.split()
        return parts[0] if parts else self.email



class Hostel(models.Model):
    CONFIRMATION_POLICY_CHOICES = [
        ('AUTO', 'Auto-Confirm on Payment'),
        ('MANUAL', 'Manual Approval Required'),
    ]
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    google_map_link = models.URLField(blank=True)
    rules = models.TextField(blank=True)
    image = models.ImageField(upload_to='hostels/', blank=True, null=True)
    manager = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_hostel',
        limit_choices_to={'role': 'HOSTEL_MANAGER'},
        help_text='The Hostel Manager responsible for this hostel.',
    )
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    facilities = models.TextField(
        blank=True,
        help_text='One facility per line (e.g. Wi-Fi, Laundry, CCTV, Generator).',
    )
    confirmation_policy = models.CharField(
        max_length=10, choices=CONFIRMATION_POLICY_CHOICES, default='AUTO',
        help_text='AUTO: booking confirmed on payment. MANAGER: manager must approve after payment.'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def facility_list(self):
        return [f.strip() for f in self.facilities.splitlines() if f.strip()]


class RoomType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    default_capacity = models.PositiveIntegerField(default=1)
    default_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    facilities = models.TextField(
        blank=True,
        help_text='One facility per line (e.g. AC, Wi-Fi, Personal Locker).',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def facility_list(self):
        return [f.strip() for f in self.facilities.splitlines() if f.strip()]


class Floor(models.Model):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='floors')
    number = models.PositiveIntegerField(help_text='Floor number (0 = ground floor).')
    name = models.CharField(max_length=50, blank=True, help_text='Optional display name, e.g. "Ground Floor".')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['hostel', 'number']
        unique_together = ('hostel', 'number')

    def __str__(self):
        return f"{self.hostel.name} - Floor {self.number}"

    @property
    def display_name(self):
        return self.name or (f'Ground Floor' if self.number == 0 else f'Floor {self.number}')


class Unit(models.Model):
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='units')
    name = models.CharField(max_length=20, help_text='Unit identifier, e.g. A or B.')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['floor__hostel', 'floor__number', 'name']
        unique_together = ('floor', 'name')

    def __str__(self):
        return f"{self.floor} - Unit {self.name}"


class Room(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('booked', 'Booked'),
        ('occupied', 'Occupied'),
        ('maintenance', 'Maintenance'),
    ]
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='rooms')
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True, related_name='rooms')
    room_type = models.ForeignKey(RoomType, on_delete=models.SET_NULL, null=True, blank=True, related_name='rooms')
    room_number = models.CharField(max_length=10)
    floor_number = models.PositiveIntegerField(default=0, editable=False, help_text='Denormalized from unit.floor.number.')
    capacity = models.IntegerField(default=1)
    max_occupancy = models.PositiveIntegerField(default=0, help_text='0 = use capacity.')
    size_sqft = models.PositiveIntegerField(null=True, blank=True)
    rent = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_ac = models.BooleanField(default=False)
    attached_bathroom = models.BooleanField(default=True)
    num_bathrooms = models.PositiveIntegerField(default=1)
    has_balcony = models.BooleanField(default=False)
    amenities = models.TextField(blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    image = models.ImageField(upload_to='rooms/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['hostel', 'room_number']

    def __str__(self):
        return f"{self.hostel.name} - Room {self.room_number}"

    def clean(self):
        if self.unit_id and self.unit.floor.hostel_id != self.hostel_id:
            raise ValidationError({'unit': 'Selected unit does not belong to the selected hostel.'})

    def save(self, *args, **kwargs):
        if self.unit_id:
            self.floor_number = self.unit.floor.number
        super().save(*args, **kwargs)

    @property
    def floor(self):
        return self.unit.floor if self.unit_id else None

    @property
    def beds_total(self):
        return self.beds.filter(is_active=True).count()

    @property
    def beds_available(self):
        return self.beds.filter(is_active=True, status='available').count()

    @property
    def occupancy_display(self):
        total = self.beds_total
        occupied = total - self.beds_available
        return f'{occupied}/{total}'

    def refresh_status(self, save=True):
        """Derive room status from its beds. Maintenance is never auto-overridden."""
        if not self.is_active:
            return self.status
        if self.status == 'maintenance':
            return self.status
        active_beds = self.beds.filter(is_active=True)
        total = active_beds.count()
        available = active_beds.filter(status='available').count()
        if total == 0:
            new_status = 'available'
        elif available == 0:
            new_status = 'occupied'
        elif available == total:
            new_status = 'available'
        else:
            new_status = 'booked'
        if new_status != self.status:
            self.status = new_status
            if save:
                Room.objects.filter(pk=self.pk).update(status=new_status)
        return self.status


class Bed(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('occupied', 'Occupied'),
        ('maintenance', 'Maintenance'),
    ]
    POSITION_CHOICES = [
        ('left', 'Left Side'),
        ('right', 'Right Side'),
        ('window', 'Window Side'),
        ('near_door', 'Near Door'),
        ('far', 'Far Side'),
    ]
    WINDOW_DIRECTION_CHOICES = [
        ('north', 'North'),
        ('south', 'South'),
        ('east', 'East'),
        ('west', 'West'),
        ('northeast', 'North-East'),
        ('northwest', 'North-West'),
        ('southeast', 'South-East'),
        ('southwest', 'South-West'),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='beds')
    bed_number = models.CharField(max_length=20, help_text='Bed label, e.g. "Bed 1".')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    is_active = models.BooleanField(default=True)

    # Physical/location information
    position = models.CharField(max_length=20, choices=POSITION_CHOICES, blank=True, help_text='Bed position in room')
    window_side = models.BooleanField(default=False, help_text='Bed is next to a window')
    window_direction = models.CharField(max_length=20, choices=WINDOW_DIRECTION_CHOICES, blank=True, help_text='Window facing direction')
    room_side = models.CharField(max_length=20, choices=POSITION_CHOICES, blank=True, help_text='Which side of room')
    near_door = models.BooleanField(default=False, help_text='Bed is near the door')
    has_charging_point = models.BooleanField(default=True, help_text='Has electrical charging point')
    has_reading_light = models.BooleanField(default=True, help_text='Has personal reading light')
    locker_number = models.CharField(max_length=30, blank=True, help_text='Assigned locker number')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['room', 'id']
        unique_together = ('room', 'bed_number')

    def __str__(self):
        return f'{self.room} - {self.bed_number}'

    @property
    def current_booking(self):
        return self.bookings.filter(status__in=['confirmed', 'checked_in']).select_related('user').first()

    def refresh_status(self, save=True):
        """Derive bed status from its active bookings. Maintenance is never auto-overridden."""
        if not self.is_active or self.status == 'maintenance':
            return self.status
        active = self.bookings.filter(status__in=['pending', 'confirmed', 'checked_in'])
        if active.filter(status='checked_in').exists():
            new_status = 'occupied'
        elif active.exists():
            new_status = 'reserved'
        else:
            new_status = 'available'
        if new_status != self.status:
            self.status = new_status
            if save:
                Bed.objects.filter(pk=self.pk).update(status=new_status)
        return self.status


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('pending_cod', 'Pending COD'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, null=True, blank=True, related_name='bookings')
    check_in = models.DateField()
    check_out = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    advance_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    booking_reference = models.CharField(max_length=20, unique=True, editable=False)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    allocation_method = models.CharField(
        max_length=20, choices=[('auto', 'Auto'), ('manager_override', 'Manager Override')],
        default='auto', blank=True
    )
    allocation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            year = datetime.now().year
            unique_id = str(uuid.uuid4()).replace('-', '').upper()[:6]
            self.booking_reference = f'NST-{year}-{unique_id}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.booking_reference

    @property
    def hostel(self):
        return self.room.hostel if self.room_id else None

    def get_active_status(self):
        """True when this booking holds its bed/room."""
        return self.status in ('pending', 'confirmed', 'checked_in')


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('sslcommerz', 'SSLCommerz'),
        ('cod', 'Cash on Delivery'),
    ]
    PAYMENT_TYPE_CHOICES = [
        ('room', 'Room Booking'),
        ('meal', 'Meal'),
    ]
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_id = models.CharField(max_length=128, unique=True, blank=True, null=True)
    validation_id = models.CharField(max_length=128, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='BDT')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='sslcommerz')
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE_CHOICES, default='room')
    payment_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.transaction_id or f'COD-{self.id}'

    def save(self, *args, **kwargs):
        # For COD payments, generate a transaction ID if not provided
        if self.payment_method == 'cod' and not self.transaction_id:
            import uuid
            self.transaction_id = f'COD-{uuid.uuid4().hex[:12].upper()}'
        super().save(*args, **kwargs)


class Cancellation(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='cancellations')
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reason = models.TextField(blank=True)
    days_before_checkin = models.IntegerField(help_text='Days between cancellation and check-in date')
    cancellation_fee = models.DecimalField(max_digits=10, decimal_places=2, help_text='Fee deducted as percentage')
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Amount to be refunded')
    created_at = models.DateTimeField(auto_now_add=True)

    CANCELLATION_FEE_TIERS = [
        (0, 0.00, 'Free cancellation (>30 days)'),
        (30, 0.10, '10% fee (15-30 days)'),
        (15, 0.25, '25% fee (7-15 days)'),
        (7, 0.50, '50% fee (3-7 days)'),
        (3, 1.00, '100% fee (<3 days)'),
    ]

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Cancellation for {self.booking.booking_reference}'

    @classmethod
    def calculate_fee(cls, days_before_checkin, amount_paid):
        if days_before_checkin > 30:
            fee_pct = 0.00
        elif days_before_checkin > 15:
            fee_pct = 0.10
        elif days_before_checkin > 7:
            fee_pct = 0.25
        elif days_before_checkin > 3:
            fee_pct = 0.50
        else:
            fee_pct = 1.00
        fee = amount_paid * Decimal(str(fee_pct))
        refund = amount_paid - fee
        return fee, refund


class Refund(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    cancellation = models.OneToOneField(Cancellation, on_delete=models.CASCADE, related_name='refund')
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_refunds'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Refund {self.status} — {self.cancellation.booking.booking_reference}'


class Complaint(models.Model):
    CATEGORY_CHOICES = [
        ('maintenance', 'Maintenance'),
        ('cleaning', 'Cleaning'),
        ('noise', 'Noise'),
        ('electricity', 'Electricity'),
        ('plumbing', 'Plumbing'),
        ('internet', 'Internet'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaints')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    hostel = models.ForeignKey(
        Hostel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='complaints', help_text='Auto-set from the renter room/booking.',
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_complaints'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.hostel_id:
            if self.room_id and self.room.unit_id:
                self.hostel = self.room.unit.floor.hostel
            else:
                active = self.user.bookings.filter(
                    status__in=['confirmed', 'checked_in']
                ).select_related('room__unit__floor__hostel').first() if self.user_id else None
                if active:
                    self.hostel = active.room.unit.floor.hostel
        super().save(*args, **kwargs)

    def __str__(self):
        return self.subject


# NOTE: The models below are LEGACY and kept only to avoid destructive migrations.
# Touch and Solve (TNS) has no Employee / Payroll / Attendance modules; these tables are unused
# by the application and hidden from the UI. Do not build on top of them.
class Employee(models.Model):
    POSITION_CHOICES = [
        ('caretaker', 'Caretaker'),
        ('cleaner', 'Cleaner'),
        ('security_guard', 'Security Guard'),
        ('receptionist', 'Receptionist'),
        ('manager', 'Manager'),
        ('other', 'Other'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employee_profile')
    employee_id = models.CharField(max_length=20, unique=True, editable=False)
    position = models.CharField(max_length=20, choices=POSITION_CHOICES)
    phone = models.CharField(max_length=20)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    joining_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.employee_id:
            unique_id = str(uuid.uuid4()).replace('-', '').upper()[:4]
            self.employee_id = f'EMP-{unique_id}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.employee_id


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('half_day', 'Half Day'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']


class SalaryPayment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    month = models.CharField(max_length=7, help_text='Format: YYYY-MM (e.g. 2026-07)')
    payment_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='paid')
    transaction_id = models.CharField(max_length=128, blank=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.month}"


class Notice(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General'),
        ('emergency', 'Emergency'),
        ('maintenance', 'Maintenance'),
        ('notice', 'Notice'),
    ]
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    hostel = models.ForeignKey(
        Hostel, on_delete=models.CASCADE, null=True, blank=True,
        related_name='notices', help_text='Leave empty for a platform-wide notice.',
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Visitor(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    hostel = models.ForeignKey(
        Hostel, on_delete=models.CASCADE,
        null=True, blank=True, related_name='visitor_logs',
        help_text='Hostel whose gate the visitor entered through.',
    )
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='visitors'
    )
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    purpose = models.CharField(max_length=200, blank=True)
    entry_time = models.DateTimeField(auto_now_add=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    is_inside = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ============================================================
# MEAL MANAGEMENT
# ============================================================

class MealSettings(models.Model):
    DEFAULT_STATUS_CHOICES = [('on', 'On'), ('off', 'Off')]

    hostel = models.OneToOneField(Hostel, on_delete=models.CASCADE, related_name='meal_settings')
    is_enabled = models.BooleanField(default=False)
    default_status = models.CharField(max_length=3, choices=DEFAULT_STATUS_CHOICES, default='on')
    cutoff_hours = models.PositiveIntegerField(default=12, help_text='Hours before meal time to lock the toggle')
    rate_breakfast = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    rate_lunch = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    rate_dinner = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Meal Settings - {self.hostel.name}"


class MealPreference(models.Model):
    MEAL_TYPES = [('breakfast', 'Breakfast'), ('lunch', 'Lunch'), ('dinner', 'Dinner')]
    STATUS_CHOICES = [('on', 'On'), ('off', 'Off')]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='meal_preferences')
    date = models.DateField()
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPES)
    status = models.CharField(max_length=3, choices=STATUS_CHOICES, default='on')
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('booking', 'date', 'meal_type')
        ordering = ['date', 'meal_type']

    def __str__(self):
        return f"{self.booking.user.full_name} - {self.date} - {self.meal_type} - {self.status}"


class MealBill(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='meal_bills')
    date = models.DateField(help_text='Date of the meal bill', default=timezone.now)
    month = models.CharField(max_length=7, help_text='YYYY-MM format', editable=False)
    total_breakfasts = models.PositiveIntegerField(default=0)
    total_lunches = models.PositiveIntegerField(default=0)
    total_dinners = models.PositiveIntegerField(default=0)
    breakfast_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lunch_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dinner_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='meal_bills')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('booking', 'date')
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if self.date and not self.month:
            self.month = self.date.strftime('%Y-%m')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Meal Bill - {self.booking.user.full_name} - {self.date}"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('meal_due', 'Meal Payment Due'),
        ('meal_overdue', 'Meal Payment Overdue'),
        ('meal_paid', 'Meal Payment Successful'),
        ('general', 'General'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_bill = models.ForeignKey(MealBill, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.full_name} - {self.get_type_display()}"
