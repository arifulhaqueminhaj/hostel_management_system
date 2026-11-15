"""
Centralised queryset/object-level access control.

Every manager-scoped view MUST filter through these helpers so that a
manager can never reach another hostel's data, even by guessing IDs.
Super Admin bypasses scoping and sees everything.
"""
from django.core.exceptions import PermissionDenied

from .models import (
    Bed, Booking, Complaint, Floor, Hostel, MealBill, Notice,
    Payment, Refund, Room, Unit, Visitor,
)

ACTIVE_BOOKING_STATUSES = ['pending', 'confirmed', 'checked_in']


def get_manager_hostel(user):
    """Return the hostel assigned to a manager, or None."""
    if not getattr(user, 'is_authenticated', False):
        return None
    if user.role == 'HOSTEL_MANAGER':
        return Hostel.objects.filter(manager=user).first()
    return None


def visible_hostels(user):
    """Queryset of hostels this user may see."""
    if not getattr(user, 'is_authenticated', False):
        return Hostel.objects.none()
    if user.role == 'SUPER_ADMIN':
        return Hostel.objects.all()
    if user.role == 'HOSTEL_MANAGER':
        return Hostel.objects.filter(manager=user)
    return Hostel.objects.filter(is_active=True)


def require_manager_hostel(user):
    """Raise PermissionDenied unless the user is a manager WITH an assigned hostel."""
    hostel = get_manager_hostel(user)
    if hostel is None:
        raise PermissionDenied('No hostel is assigned to your account.')
    return hostel


def visible_rooms(user):
    qs = Room.objects.select_related(
        'hostel', 'room_type', 'unit', 'unit__floor',
    )
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(hostel__manager=user)
    return qs.filter(is_active=True, hostel__is_active=True)


def visible_floors(user):
    qs = Floor.objects.select_related('hostel')
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(hostel__manager=user)
    return qs.filter(hostel__is_active=True)


def visible_units(user):
    qs = Unit.objects.select_related('floor', 'floor__hostel')
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(floor__hostel__manager=user)
    return qs.filter(floor__hostel__is_active=True)


def visible_beds(user):
    qs = Bed.objects.select_related('room', 'room__unit__floor__hostel')
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(room__hostel__manager=user)
    return qs.filter(status='available', is_active=True, room__is_active=True)


def visible_bookings(user):
    qs = Booking.objects.select_related(
        'user', 'bed', 'room', 'room__hostel',
        'room__unit', 'room__unit__floor',
    )
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(room__hostel__manager=user)
    return qs.filter(user=user)


def visible_payments(user):
    qs = Payment.objects.select_related('booking', 'user')
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        # Payments tied to bookings in the manager's hostel (meal-bill payments
        # without a booking are excluded for managers).
        return qs.filter(booking__room__hostel__manager=user).distinct()
    return qs.filter(user=user)


def visible_complaints(user):
    qs = Complaint.objects.select_related('user', 'assigned_to', 'room', 'hostel')
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(hostel__manager=user)
    return qs.filter(user=user)


def visible_notices(user):
    from django.db.models import Q
    qs = Notice.objects.filter(is_active=True).select_related('hostel', 'created_by')
    if not getattr(user, 'is_authenticated', False):
        return qs.filter(hostel__isnull=True)
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        hostel = get_manager_hostel(user)
        if hostel:
            return qs.filter(Q(hostel__isnull=True) | Q(hostel=hostel))
        return qs.filter(hostel__isnull=True)
    renter_hostels = Hostel.objects.filter(
        rooms__bookings__user=user,
        rooms__bookings__status__in=ACTIVE_BOOKING_STATUSES,
    )
    return qs.filter(Q(hostel__isnull=True) | Q(hostel__in=renter_hostels))


def visible_visitors(user):
    qs = Visitor.objects.select_related('host', 'room')
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(room__hostel__manager=user)
    return qs.filter(host=user)


def visible_meal_bills(user):
    qs = MealBill.objects.select_related('booking__user', 'booking__room__hostel')
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(booking__room__hostel__manager=user)
    return qs.filter(booking__user=user)


def visible_refunds(user):
    qs = Refund.objects.select_related(
        'cancellation__booking__user', 'cancellation__booking__room__hostel', 'payment', 'processed_by',
    )
    if user.role == 'SUPER_ADMIN':
        return qs
    if user.role == 'HOSTEL_MANAGER':
        return qs.filter(cancellation__booking__room__hostel__manager=user)
    return qs.filter(cancellation__booking__user=user)


def can_manage_room(user, room):
    if user.role == 'SUPER_ADMIN':
        return True
    if user.role == 'HOSTEL_MANAGER':
        return room.hostel.manager_id == user.id
    return False


def can_view_room(user, room):
    if can_manage_room(user, room):
        return True
    return bool(room.is_active and room.hostel.is_active)
