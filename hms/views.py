from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.db import transaction
from django.db.models import Sum, Count, Q, Prefetch
from django.db.models.functions import TruncMonth
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from datetime import date, datetime, timedelta
from decimal import Decimal
import json, uuid, requests, io, calendar, re

from .models import (
    User, Hostel, RoomType, Floor, Unit, Room, Bed,
    Booking, Payment, Complaint, Notice, Visitor,
    MealSettings, MealPreference, MealBill, Notification,
    Cancellation, Refund,
)
from .forms import (
    LoginForm, RenterRegistrationForm, ProfileUpdateForm,
    HostelForm, HostelManagerAssignForm, RoomTypeForm,
    FloorForm, UnitForm, RoomForm, BedForm,
    BookingForm, ComplaintForm, NoticeForm, VisitorForm,
    AllocationOverrideForm,
    MealSettingsForm,
    ManagerCreateForm, ManagerEditForm,
)
from .decorators import admin_required, manager_required, renter_required
from . import access


def generate_transaction_id():
    return f'TXN-{uuid.uuid4().hex[:12].upper()}'


# ============================================================
# 1. AUTH VIEWS
# ============================================================

def login_view(request):
    if request.user.is_authenticated:
        if request.user.must_change_password:
            return redirect('change_password')
        return redirect('dashboard_home')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(email=email, password=password)
            if user:
                login(request, user)
                if user.must_change_password:
                    messages.warning(request, 'Please change your password before continuing.')
                    return redirect('change_password')
                messages.success(request, f'Welcome back, {user.full_name}!')
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('dashboard_home')
            messages.error(request, 'Invalid email or password.')
        else:
            messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})


def _role_login_view(request, allowed_role, template_name, role_display):
    """Generic role-specific login"""
    if request.user.is_authenticated:
        if request.user.must_change_password:
            return redirect("change_password")
        return redirect("dashboard_home")
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(email=email, password=password)
            if user:
                if user.role != allowed_role:
                    messages.error(request, f"This login is for {role_display} only. Your account is registered as {user.get_role_display()}.")
                    return render(request, template_name, {"form": form, "role": role_display})
                login(request, user)
                if user.must_change_password:
                    messages.warning(request, "Please change your password before continuing.")
                    return redirect("change_password")
                messages.success(request, f"Welcome back, {user.full_name}!")
                return redirect("dashboard_home")
            messages.error(request, "Invalid email or password.")
        else:
            messages.error(request, "Invalid email or password.")
    else:
        form = LoginForm()
    return render(request, template_name, {"form": form, "role": role_display})

def super_admin_login(request):
    return _role_login_view(request, "SUPER_ADMIN", "login_super_admin.html", "Super Admin")

def employee_login(request):
    return _role_login_view(request, "HOSTEL_MANAGER", "login_employee.html", "Manager")

def renter_login(request):
    return _role_login_view(request, "RENTER", "login_renter.html", "Renter")


def employee_register(request):
    messages.error(request, 'Manager self-registration is disabled. Please contact your administrator.')
    return redirect('index')



def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def change_password_view(request):
    if request.method == 'POST':
        current = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')

        if not request.user.check_password(current):
            messages.error(request, 'Current password is incorrect.')
            return render(request, 'change_password.html')

        if new_password != confirm:
            messages.error(request, 'New passwords do not match.')
            return render(request, 'change_password.html')

        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'change_password.html')
        if not re.search(r'[A-Z]', new_password):
            messages.error(request, 'Password must contain at least one uppercase letter.')
            return render(request, 'change_password.html')
        if not re.search(r'[a-z]', new_password):
            messages.error(request, 'Password must contain at least one lowercase letter.')
            return render(request, 'change_password.html')
        if not re.search(r'\d', new_password):
            messages.error(request, 'Password must contain at least one digit.')
            return render(request, 'change_password.html')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password):
            messages.error(request, 'Password must contain at least one special character.')
            return render(request, 'change_password.html')

        request.user.set_password(new_password)
        request.user.must_change_password = False
        request.user.save()
        messages.success(request, 'Password changed successfully. Please log in with your new password.')
        return redirect('login')

    return render(request, 'change_password.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_home')
    if request.method == 'POST':
        form = RenterRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'RENTER'
            user.set_password(form.cleaned_data['password'])
            user.save()
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to Touch and Solve (TNS).')
            return redirect('dashboard_home')
    else:
        form = RenterRegistrationForm()
    return render(request, 'register.html', {'form': form})


@login_required
def profile_view(request):
    return render(request, 'profile.html', {'profile_user': request.user})


@login_required
def edit_profile_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, 'edit_profile.html', {'form': form})


# ============================================================
# 2. PUBLIC VIEWS
# ============================================================

def index(request):
    """Public home page: visitors can browse hostels and rooms without logging in."""
    hostels = Hostel.objects.filter(is_active=True)[:6]

    # Main hostel overview (single-hostel system).
    hostel = Hostel.objects.filter(slug='nestora-hostel', is_active=True).first()
    if hostel:
        beds_total = Bed.objects.filter(room__hostel=hostel, is_active=True).count()
        beds_available = Bed.objects.filter(room__hostel=hostel, is_active=True, status='available').count()
        beds_occupied = Bed.objects.filter(room__hostel=hostel, is_active=True, status='occupied').count()
        occupancy_pct = round((beds_occupied / beds_total) * 100) if beds_total else 0
        hostel_view = {
            'hostel': hostel,
            'beds_total': beds_total,
            'beds_available': beds_available,
            'beds_occupied': beds_occupied,
            'occupancy_pct': occupancy_pct,
        }
    else:
        hostel_view = None

    # Public room showcase (first 9 active rooms).
    room_ids = list(
        Room.objects.filter(hostel__is_active=True, is_active=True)
        .order_by('unit__floor__number', 'unit__name', 'room_number')
        .values_list('id', flat=True)[:9]
    )
    rooms = (
        Room.objects.filter(pk__in=room_ids)
        .select_related('room_type', 'unit', 'unit__floor')
        .annotate(
            beds_total_annotated=Count('beds', filter=Q(beds__is_active=True)),
            beds_free_annotated=Count('beds', filter=Q(beds__is_active=True, beds__status='available')),
        )
        .order_by('unit__floor__number', 'unit__name', 'room_number')
    )

    stats = {
        'total_hostels': Hostel.objects.filter(is_active=True).count(),
        'total_rooms': Room.objects.filter(hostel__is_active=True, is_active=True).count(),
        'total_renters': User.objects.filter(role='RENTER', is_active=True).count(),
        'total_available': Room.objects.filter(hostel__is_active=True, is_active=True, status='available').count(),
    }

    return render(request, 'index.html', {
        'hostels': hostels,
        'hostel_view': hostel_view,
        'rooms': rooms,
        'stats': stats,
    })


def about(request):
    return render(request, 'about.html')


# ============================================================
# 3. HOSTEL VIEWS
# ============================================================

def hostel_list(request):
    """Redirect to the single Touch and Solve (TNS) Hostel detail page."""
    nestora = Hostel.objects.filter(slug='nestora-hostel').first()
    if nestora:
        return redirect('hostel_detail', slug=nestora.slug)
    messages.error(request, 'Touch and Solve (TNS) Hostel not found.')
    return redirect('index')


@login_required
@admin_required
def hostel_add(request):
    """Hostel creation is disabled in single-hostel mode."""
    messages.error(request, 'Hostel creation is disabled. This is a single-hostel system.')
    return redirect('hostel_list')


def _get_hostel_for_user(request, slug):
    """Fetch a hostel enforcing manager scoping (404 when out of scope).

    Anonymous visitors may view the active single hostel (public browsing)."""
    if not request.user.is_authenticated:
        return get_object_or_404(
            Hostel.objects.filter(is_active=True).annotate(
                room_count=Count('rooms'),
                available_rooms=Count('rooms', filter=Q(rooms__status='available')),
            ),
            slug=slug,
        )
    queryset = access.visible_hostels(request.user)
    return get_object_or_404(
        queryset.annotate(
            room_count=Count('rooms'),
            available_rooms=Count('rooms', filter=Q(rooms__status='available')),
        ),
        slug=slug,
    )


def hostel_detail(request, slug):
    hostel = _get_hostel_for_user(request, slug)
    floors = (
        Floor.objects.filter(hostel=hostel)
        .prefetch_related(
            Prefetch('units', queryset=Unit.objects.prefetch_related('rooms'))
        )
    )
    beds_total = Bed.objects.filter(room__hostel=hostel, is_active=True).count()
    beds_available = Bed.objects.filter(room__hostel=hostel, is_active=True, status='available').count()
    beds_occupied = Bed.objects.filter(room__hostel=hostel, is_active=True, status='occupied').count()
    rooms = hostel.rooms.filter(is_active=True).select_related('unit', 'unit__floor', 'room_type')
    units_count = Unit.objects.filter(floor__hostel=hostel).count()
    occupancy_pct = round((beds_occupied / beds_total) * 100) if beds_total else 0
    return render(request, 'hostels/hostel_detail.html', {
        'hostel': hostel, 'floors': floors, 'rooms': rooms,
        'beds_total': beds_total, 'beds_available': beds_available,
        'beds_occupied': beds_occupied, 'units_count': units_count,
        'occupancy_pct': occupancy_pct,
    })


@login_required
@admin_required
def hostel_edit(request, slug):
    hostel = get_object_or_404(access.visible_hostels(request.user), slug=slug)
    if request.method == 'POST':
        form = HostelForm(request.POST, request.FILES, instance=hostel)
        if form.is_valid():
            form.save()
            messages.success(request, f'Hostel "{hostel.name}" updated successfully.')
            return redirect('hostel_detail', slug=hostel.slug)
    else:
        form = HostelForm(instance=hostel)
    return render(request, 'hostels/hostel_form.html', {'form': form, 'title': 'Edit Hostel'})


@login_required
@admin_required
def hostel_delete(request, slug):
    hostel = get_object_or_404(Hostel, slug=slug)
    if request.method == 'POST':
        if Booking.objects.filter(room__hostel=hostel, status__in=['pending', 'confirmed', 'checked_in']).exists():
            messages.error(request, 'This hostel has active bookings and cannot be deleted.')
            return redirect('hostel_detail', slug=hostel.slug)
        try:
            with transaction.atomic():
                Room.objects.filter(hostel=hostel).delete()  # beds cascade; unit is PROTECT
                hostel.delete()
        except ProtectedError:
            messages.error(request, 'This hostel still has related records and cannot be deleted.')
            return redirect('hostel_detail', slug=hostel.slug)
        messages.success(request, 'Hostel deleted successfully.')
        return redirect('hostel_list')
    return render(request, 'hostels/hostel_confirm_delete.html', {'hostel': hostel})


@login_required
@admin_required
def assign_manager(request, slug):
    """Super Admin assigns / replaces / removes the manager of a hostel."""
    hostel = get_object_or_404(Hostel, slug=slug)
    if request.method == 'POST':
        form = HostelManagerAssignForm(request.POST, instance=hostel)
        if form.is_valid():
            old_manager = Hostel.objects.get(pk=hostel.pk).manager
            new_manager = form.cleaned_data['manager']
            if old_manager and old_manager != new_manager:
                # A manager can only run one hostel at a time.
                Hostel.objects.filter(manager=old_manager).update(manager=None)
            form.save()
            if new_manager:
                messages.success(request, f'{new_manager.full_name} assigned as manager of {hostel.name}.')
            else:
                messages.success(request, f'Manager removed from {hostel.name}.')
            return redirect('hostel_detail', slug=hostel.slug)
    else:
        form = HostelManagerAssignForm(instance=hostel)
    return render(request, 'hostels/assign_manager.html', {'form': form, 'hostel': hostel})


# ============================================================
# 4. STRUCTURE VIEWS (FLOORS / UNITS / ROOMS / BEDS / TYPES)
# ============================================================

# ---------- Floors ----------

@login_required
@manager_required
def floor_list(request, hostel_id):
    if request.user.role == 'HOSTEL_MANAGER' and not Hostel.objects.filter(pk=hostel_id, manager=request.user).exists():
        raise PermissionDenied('This hostel is not assigned to you.')
    hostel = get_object_or_404(Hostel, pk=hostel_id)
    floors = (
        Floor.objects.filter(hostel=hostel)
        .annotate(unit_count=Count('units'), room_count=Count('units__rooms'))
        .prefetch_related('units')
    )
    return render(request, 'structure/floor_list.html', {'hostel': hostel, 'floors': floors})


@login_required
@manager_required
def floor_add(request, hostel_id):
    if request.user.role == 'HOSTEL_MANAGER' and not Hostel.objects.filter(pk=hostel_id, manager=request.user).exists():
        raise PermissionDenied('This hostel is not assigned to you.')
    hostel = get_object_or_404(Hostel, pk=hostel_id)
    if request.method == 'POST':
        form = FloorForm(request.POST)
        if form.is_valid():
            number = form.cleaned_data['number']
            if Floor.objects.filter(hostel=hostel, number=number).exists():
                form.add_error('number', f'Floor {number} already exists in this hostel.')
            else:
                floor = form.save(commit=False)
                floor.hostel = hostel
                floor.save()
                messages.success(request, f'{floor.display_name} added to {hostel.name}.')
                return redirect('floor_list', hostel_id=hostel.pk)
    else:
        form = FloorForm()
    return render(request, 'structure/floor_form.html', {'form': form, 'hostel': hostel, 'title': 'Add Floor'})


@login_required
@manager_required
def floor_edit(request, pk):
    floor = get_object_or_404(access.visible_floors(request.user), pk=pk)
    if request.method == 'POST':
        form = FloorForm(request.POST, instance=floor)
        if form.is_valid():
            number = form.cleaned_data['number']
            if Floor.objects.filter(hostel=floor.hostel, number=number).exclude(pk=floor.pk).exists():
                form.add_error('number', f'Floor {number} already exists in this hostel.')
            else:
                floor = form.save()
                # Keep denormalized room.floor_number in sync.
                floor.units.all().update()  # no-op touch
                Room.objects.filter(unit__floor=floor).update(floor_number=number)
                messages.success(request, f'{floor.display_name} updated.')
                return redirect('floor_list', hostel_id=floor.hostel_id)
    else:
        form = FloorForm(instance=floor)
    return render(request, 'structure/floor_form.html', {'form': form, 'hostel': floor.hostel, 'title': 'Edit Floor'})


@login_required
@manager_required
def floor_delete(request, pk):
    floor = get_object_or_404(access.visible_floors(request.user), pk=pk)
    hostel_id = floor.hostel_id
    if request.method == 'POST':
        if floor.units.exists():
            messages.error(request, 'Delete all units under this floor first.')
            return redirect('floor_list', hostel_id=hostel_id)
        floor.delete()
        messages.success(request, 'Floor deleted successfully.')
        return redirect('floor_list', hostel_id=hostel_id)
    return render(request, 'structure/floor_confirm_delete.html', {'floor': floor})


# ---------- Units ----------

@login_required
@manager_required
def unit_list(request, floor_id):
    floor = get_object_or_404(access.visible_floors(request.user), pk=floor_id)
    units = floor.units.annotate(room_count=Count('rooms'))
    return render(request, 'structure/unit_list.html', {'floor': floor, 'units': units})


@login_required
@manager_required
def unit_add(request, floor_id):
    floor = get_object_or_404(access.visible_floors(request.user), pk=floor_id)
    if request.method == 'POST':
        form = UnitForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            if Unit.objects.filter(floor=floor, name=name).exists():
                form.add_error('name', f'Unit {name} already exists on this floor.')
            else:
                unit = form.save(commit=False)
                unit.floor = floor
                unit.save()
                messages.success(request, f'Unit {unit.name} added to {floor.display_name}.')
                return redirect('unit_list', floor_id=floor.pk)
    else:
        form = UnitForm()
    return render(request, 'structure/unit_form.html', {'form': form, 'floor': floor, 'title': 'Add Unit'})


@login_required
@manager_required
def unit_edit(request, pk):
    unit = get_object_or_404(access.visible_units(request.user), pk=pk)
    if request.method == 'POST':
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            name = form.cleaned_data['name']
            if Unit.objects.filter(floor=unit.floor, name=name).exclude(pk=unit.pk).exists():
                form.add_error('name', f'Unit {name} already exists on this floor.')
            else:
                form.save()
                messages.success(request, f'Unit {name} updated.')
                return redirect('unit_list', floor_id=unit.floor_id)
    else:
        form = UnitForm(instance=unit)
    return render(request, 'structure/unit_form.html', {'form': form, 'floor': unit.floor, 'title': 'Edit Unit'})


@login_required
@manager_required
def unit_delete(request, pk):
    unit = get_object_or_404(access.visible_units(request.user), pk=pk)
    floor_id = unit.floor_id
    if request.method == 'POST':
        if unit.rooms.exists():
            messages.error(request, 'Delete or move all rooms under this unit first.')
            return redirect('unit_list', floor_id=floor_id)
        unit.delete()
        messages.success(request, 'Unit deleted successfully.')
        return redirect('unit_list', floor_id=floor_id)
    return render(request, 'structure/unit_confirm_delete.html', {'unit': unit})


# ---------- Room types ----------

@login_required
@admin_required
def room_type_list(request):
    room_types = RoomType.objects.annotate(room_count=Count('rooms'))
    return render(request, 'structure/room_type_list.html', {'room_types': room_types})


@login_required
@admin_required
def room_type_add(request):
    if request.method == 'POST':
        form = RoomTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Room type "{form.cleaned_data["name"]}" created.')
            return redirect('room_type_list')
    else:
        form = RoomTypeForm()
    return render(request, 'structure/room_type_form.html', {'form': form, 'title': 'Add Room Type'})


@login_required
@admin_required
def room_type_edit(request, pk):
    room_type = get_object_or_404(RoomType, pk=pk)
    if request.method == 'POST':
        form = RoomTypeForm(request.POST, instance=room_type)
        if form.is_valid():
            form.save()
            messages.success(request, 'Room type updated.')
            return redirect('room_type_list')
    else:
        form = RoomTypeForm(instance=room_type)
    return render(request, 'structure/room_type_form.html', {'form': form, 'title': 'Edit Room Type'})


@login_required
@admin_required
def room_type_delete(request, pk):
    room_type = get_object_or_404(RoomType, pk=pk)
    if request.method == 'POST':
        if room_type.rooms.exists():
            messages.error(request, 'This room type is used by rooms and cannot be deleted.')
        else:
            room_type.delete()
            messages.success(request, 'Room type deleted.')
        return redirect('room_type_list')
    return render(request, 'structure/room_type_confirm_delete.html', {'room_type': room_type})


# ---------- Rooms ----------

def room_list(request):
    rooms = access.visible_rooms(request.user).order_by('hostel__name', 'room_number')
    status_filter = request.GET.get('status')
    type_filter = request.GET.get('type')
    q = request.GET.get('q', '')
    if status_filter:
        rooms = rooms.filter(status=status_filter)
    if type_filter:
        rooms = rooms.filter(room_type_id=type_filter)
    if q:
        rooms = rooms.filter(room_number__icontains=q)
    room_types = RoomType.objects.filter(is_active=True)
    paginator = Paginator(rooms, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'rooms/room_list.html', {
        'page_obj': page_obj, 'rooms': page_obj.object_list,
        'room_types': room_types,
        'selected_status': status_filter,
        'selected_type': type_filter, 'query': q,
    })


@login_required
@manager_required
def room_add(request):
    if request.user.role == 'HOSTEL_MANAGER' and access.get_manager_hostel(request.user) is None:
        raise PermissionDenied('No hostel is assigned to your account.')
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                room = form.save(commit=False)
                num_beds = form.cleaned_data.get('num_beds') or 0
                room.save()
                for i in range(1, num_beds + 1):
                    Bed.objects.create(room=room, bed_number=f'Bed {i}')
            messages.success(request, f'Room {room.room_number} added with {num_beds} bed(s).')
            return redirect('room_detail', pk=room.pk)
    else:
        form = RoomForm(user=request.user)
    return render(request, 'rooms/room_form.html', {'form': form, 'title': 'Add Room'})


def room_detail(request, pk):
    room = get_object_or_404(
        Room.objects.select_related('hostel', 'room_type', 'unit', 'unit__floor'),
        pk=pk,
    )
    if request.user.is_authenticated and not access.can_view_room(request.user, room):
        raise PermissionDenied('You do not have access to this room.')
    beds = room.beds.filter(is_active=True).prefetch_related(
        Prefetch('bookings', queryset=Booking.objects.filter(status__in=['confirmed', 'checked_in']).select_related('user'))
    )
    facilities = []
    if room.room_type:
        facilities.extend(room.room_type.facility_list)
    facilities.extend([a.strip() for a in room.amenities.splitlines() if a.strip()])
    return render(request, 'rooms/room_detail.html', {
        'room': room, 'beds': beds, 'facilities': facilities,
    })


@login_required
@manager_required
def room_edit(request, pk):
    room = get_object_or_404(access.visible_rooms(request.user), pk=pk)
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES, instance=room, user=request.user)
        if form.is_valid():
            form.save()
            room.refresh_status()
            messages.success(request, f'Room {room.room_number} updated successfully.')
            return redirect('room_detail', pk=room.pk)
    else:
        form = RoomForm(instance=room, user=request.user)
    return render(request, 'rooms/room_form.html', {'form': form, 'title': 'Edit Room', 'room': room})


@login_required
@manager_required
def room_delete(request, pk):
    room = get_object_or_404(access.visible_rooms(request.user), pk=pk)
    if request.method == 'POST':
        if room.bookings.filter(status__in=['pending', 'confirmed', 'checked_in']).exists():
            messages.error(request, 'This room has active bookings and cannot be deleted.')
            return redirect('room_detail', pk=room.pk)
        room.delete()
        messages.success(request, 'Room deleted successfully.')
        return redirect('room_list')
    return render(request, 'rooms/room_confirm_delete.html', {'room': room})


# ---------- Beds ----------

@login_required
@manager_required
def bed_manage(request, room_id):
    """Add/edit/delete beds of one room (manager scoped)."""
    room = get_object_or_404(access.visible_rooms(request.user), pk=room_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            form = BedForm(request.POST)
            if form.is_valid():
                bed = form.save(commit=False)
                bed.room = room
                try:
                    bed.full_clean(exclude=['room'])
                    bed.save()
                    room.refresh_status()
                    messages.success(request, f'{bed.bed_number} added to room {room.room_number}.')
                except Exception as e:
                    messages.error(request, f'Could not add bed: {e.message if hasattr(e, "message") else e}')
            else:
                messages.error(request, 'Invalid bed data.')
        elif action == 'toggle_status':
            bed = get_object_or_404(Bed, pk=request.POST.get('bed_id'), room=room)
            new_status = request.POST.get('status')
            if new_status in dict(Bed.STATUS_CHOICES):
                if bed.status == 'occupied' and new_status != 'occupied':
                    active = bed.bookings.filter(status__in=['confirmed', 'checked_in']).first()
                    if active:
                        messages.error(request, f'{bed.bed_number} is held by booking {active.booking_reference}. Cancel/check-out that booking first.')
                        return redirect('bed_manage', room_id=room.pk)
                bed.status = new_status
                bed.save()
                room.refresh_status()
                messages.success(request, f'{bed.bed_number} marked as {bed.get_status_display().lower()}.')
        elif action == 'delete':
            bed = get_object_or_404(Bed, pk=request.POST.get('bed_id'), room=room)
            if bed.bookings.filter(status__in=['pending', 'confirmed', 'checked_in']).exists():
                messages.error(request, f'{bed.bed_number} has active bookings and cannot be removed.')
            else:
                bed.delete()
                room.refresh_status()
                messages.success(request, f'{bed.bed_number} removed from room {room.room_number}.')
        return redirect('bed_manage', room_id=room.pk)

    beds = room.beds.all().prefetch_related(
        Prefetch('bookings', queryset=Booking.objects.filter(status__in=['confirmed', 'checked_in']).select_related('user'))
    )
    next_label = f'Bed {room.beds.count() + 1}'
    return render(request, 'structure/bed_manage.html', {
        'room': room, 'beds': beds, 'form': BedForm(initial={'bed_number': next_label}),
    })


# ============================================================
# 5. SEARCH & AVAILABILITY VIEWS
# ============================================================

@login_required
def search_rooms(request):
    """Find Your Room - search available rooms in Touch and Solve (TNS) Hostel with date-aware availability."""
    hostel = Hostel.objects.filter(slug='nestora-hostel', is_active=True).first()
    if not hostel:
        messages.error(request, 'Touch and Solve (TNS) Hostel not found.')
        return redirect('index')

    def _clean_none(value):
        """Convert 'None' string to None."""
        if value in ('None', 'none', ''):
            return None
        return value

    check_in = _clean_none(request.GET.get('check_in'))
    check_out = _clean_none(request.GET.get('check_out'))
    floor_id = _clean_none(request.GET.get('floor'))
    unit_id = _clean_none(request.GET.get('unit'))
    type_filter = _clean_none(request.GET.get('type'))
    min_price = _clean_none(request.GET.get('min_price'))
    max_price = _clean_none(request.GET.get('max_price'))
    q = request.GET.get('q', '')

    rooms = Room.objects.filter(hostel=hostel, is_active=True).select_related('room_type', 'unit', 'unit__floor')

# Date-aware availability: only show rooms with at least one bed free for the given dates
    if check_in and check_out:
        overlapping_beds = Bed.objects.filter(
            room__hostel=hostel,
            is_active=True,
            bookings__status__in=['pending', 'confirmed', 'checked_in'],
            bookings__check_in__lt=check_out,
            bookings__check_out__gt=check_in,
        ).values_list('id', flat=True)
        rooms = rooms.annotate(
            beds_total_annotated=Count('beds', filter=Q(beds__is_active=True)),
            beds_free_annotated=Count('beds', filter=Q(beds__is_active=True) & ~Q(beds__id__in=overlapping_beds)),
        ).filter(beds_free_annotated__gt=0)
    else:
        # No dates provided: show rooms with any available bed
        rooms = rooms.annotate(
            beds_total_annotated=Count('beds', filter=Q(beds__is_active=True)),
            beds_free_annotated=Count('beds', filter=Q(beds__is_active=True, beds__status='available')),
        ).filter(beds_free_annotated__gt=0)

    if floor_id:
        rooms = rooms.filter(unit__floor_id=floor_id)
    if unit_id:
        rooms = rooms.filter(unit_id=unit_id)
    if type_filter:
        rooms = rooms.filter(room_type_id=type_filter)
    if min_price:
        try:
            rooms = rooms.filter(rent__gte=Decimal(min_price))
        except Exception:
            pass
    if max_price:
        try:
            rooms = rooms.filter(rent__lte=Decimal(max_price))
        except Exception:
            pass
    if q:
        rooms = rooms.filter(
            Q(room_number__icontains=q) |
            Q(room_type__name__icontains=q) |
            Q(unit__name__icontains=q) |
            Q(unit__floor__name__icontains=q)
        )

    rooms = rooms.order_by('unit__floor__number', 'unit__name', 'room_number')

    floors = Floor.objects.filter(hostel=hostel).prefetch_related('units')
    units = Unit.objects.filter(floor__hostel=hostel)
    room_types = RoomType.objects.filter(is_active=True)

    paginator = Paginator(rooms, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'bookings/search_rooms.html', {
        'page_obj': page_obj,
        'rooms': page_obj.object_list,
        'hostel': hostel,
        'floors': floors,
        'units': units,
        'room_types': room_types,
        'selected_floor': floor_id,
        'selected_unit': unit_id,
        'selected_type': type_filter,
        'min_price': min_price, 'max_price': max_price,
        'check_in': check_in, 'check_out': check_out,
        'query': q,
    })


@login_required
def check_availability(request):
    room_id = request.GET.get('room_id')
    check_in = request.GET.get('check_in')
    check_out = request.GET.get('check_out')
    if not all([room_id, check_in, check_out]):
        return JsonResponse({'available': False, 'error': 'Missing parameters'})
    try:
        room = Room.objects.get(pk=room_id)
        eligible = room.beds.filter(is_active=True).exclude(status='maintenance')
        overlapping = Booking.objects.filter(
            bed__room=room,
            status__in=['pending', 'confirmed', 'checked_in'],
            check_in__lt=check_out,
            check_out__gt=check_in,
        ).values_list('bed_id', flat=True)
        free = eligible.exclude(pk__in=overlapping).count()
        return JsonResponse({'available': free > 0 and room.status != 'maintenance', 'available_beds': free})
    except Room.DoesNotExist:
        return JsonResponse({'available': False, 'error': 'Room not found'})


# ============================================================
# 6. BOOKING VIEWS
# ============================================================

ACTIVE_STATUSES = ['pending', 'confirmed', 'checked_in']


def _bed_is_free(bed, check_in, check_out, exclude_booking=None):
    """A bed is bookable when physically available and no active booking overlaps the dates."""
    if not bed.is_active or bed.status != 'available':
        return False
    qs = Booking.objects.filter(
        bed=bed,
        status__in=ACTIVE_STATUSES,
        check_in__lt=check_out,
        check_out__gt=check_in,
    )
    if exclude_booking:
        qs = qs.exclude(pk=exclude_booking.pk)
    return not qs.exists()


@login_required
def create_booking(request, room_id):
    room = get_object_or_404(
        Room.objects.select_related('hostel', 'room_type', 'unit', 'unit__floor'),
        pk=room_id, is_active=True,
    )
    if request.user.role != 'RENTER':
        messages.error(request, 'Only renters can create bookings.')
        return redirect('room_detail', pk=room.pk)

    beds = list(
        room.beds.filter(is_active=True).exclude(status__in=['maintenance', 'occupied']).order_by('id')
    )

    if request.method == 'POST':
        form = BookingForm(request.POST)
        bed_id = request.POST.get('bed')
        bed = next((b for b in beds if b.pk == int(bed_id)), None) if bed_id else None
        if not bed:
            messages.error(request, 'Please select an available bed.')
            return render(request, 'bookings/create_booking.html', {
                'form': form, 'room': room, 'beds': beds,
            })
        if form.is_valid():
            check_in = form.cleaned_data['check_in']
            check_out = form.cleaned_data['check_out']

            try:
                with transaction.atomic():
                    locked_bed = Bed.objects.select_for_update().get(pk=bed.pk)
                    if not _bed_is_free(locked_bed, check_in, check_out):
                        messages.error(request, 'That bed was just taken for these dates. Please pick another.')
                        return redirect('create_booking', room_id=room.pk)

                    booking = Booking(
                        user=request.user,
                        room=room,
                        bed=locked_bed,
                        check_in=check_in,
                        check_out=check_out,
                        total_amount=room.rent,
                        status='pending',
                        payment_status='unpaid',
                    )
                    booking.save()

                    locked_bed.refresh_status()
                    room.refresh_status()
            except Exception:
                messages.error(request, 'This bed is no longer available for the selected dates.')
                return redirect('room_detail', pk=room.pk)

            messages.success(request, f'Bed {locked_bed.bed_number} in room {room.room_number} reserved. Proceed to payment.')
            return redirect('initiate_payment', booking_id=booking.id)
    else:
        form = BookingForm(initial={
            'check_in': request.GET.get('check_in'),
            'check_out': request.GET.get('check_out'),
        })

    return render(request, 'bookings/create_booking.html', {
        'form': form, 'room': room, 'beds': beds,
    })


@login_required
def my_bookings(request):
    bookings = access.visible_bookings(request.user)
    status_filter = request.GET.get('status')
    q = request.GET.get('q', '')
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    if q:
        bookings = bookings.filter(
            Q(booking_reference__icontains=q) |
            Q(room__hostel__name__icontains=q)
        )
    return render(request, 'bookings/my_bookings.html', {
        'bookings': bookings.order_by('-created_at'),
        'selected_status': status_filter, 'query': q,
    })


@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(access.visible_bookings(request.user), pk=pk)
    payments = Payment.objects.filter(booking=booking).order_by('-payment_date')
    payment = payments.first()
    cancellations = Cancellation.objects.filter(booking=booking).select_related('refund').order_by('-created_at')
    pending_refund = Refund.objects.filter(
        cancellation__booking=booking, status='pending'
    ).first()
    can_manage = request.user.role in ('SUPER_ADMIN', 'HOSTEL_MANAGER')
    return render(request, 'bookings/booking_detail.html', {
        'booking': booking, 'payment': payment, 'payments': payments,
        'cancellations': cancellations, 'pending_refund': pending_refund,
        'can_manage': can_manage,
    })


def _release_booking_resources(booking):
    """Free the bed / refresh room status after cancel, reject or checkout."""
    bed = booking.bed
    if bed:
        bed.refresh_status()
    room = booking.room
    if room:
        room.refresh_status()


@login_required
def cancel_booking(request, pk):
    booking = get_object_or_404(access.visible_bookings(request.user).select_related('bed', 'room'), pk=pk)
    if booking.status not in ['pending', 'confirmed']:
        messages.error(request, 'This booking cannot be cancelled.')
        return redirect('booking_detail', pk=booking.pk)

    today = timezone.now().date()
    days_before = (booking.check_in - today).days
    amount_paid = booking.advance_paid
    fee, refund_amount = Cancellation.calculate_fee(days_before, amount_paid)

    if booking.check_in <= today:
        days_before = 0
        fee = amount_paid
        refund_amount = Decimal('0.00')

    if request.method == 'POST':
        cancellation = Cancellation.objects.create(
            booking=booking,
            cancelled_by=request.user,
            reason=request.POST.get('reason', ''),
            days_before_checkin=max(days_before, 0),
            cancellation_fee=fee,
            refund_amount=refund_amount,
        )
        if refund_amount > 0:
            payment = Payment.objects.filter(booking=booking, status='success').first()
            if payment:
                Refund.objects.create(
                    cancellation=cancellation,
                    payment=payment,
                    amount=refund_amount,
                    status='pending',
                )
                payment.status = 'refunded'
                payment.save()

        booking.status = 'cancelled'
        booking.payment_status = 'refunded' if refund_amount > 0 else 'paid'
        booking.save()
        _release_booking_resources(booking)

        messages.success(request, f'Booking cancelled. Refund amount: à§³{refund_amount}.')
        return redirect('booking_detail', pk=booking.pk)

    payments = Payment.objects.filter(booking=booking).order_by('-payment_date')
    return render(request, 'bookings/cancel_booking.html', {
        'booking': booking,
        'days_before': max(days_before, 0),
        'cancellation_fee': fee,
        'refund_amount': refund_amount,
        'amount_paid': amount_paid,
        'payments': payments,
    })


@login_required
@manager_required
def all_bookings(request):
    bookings = access.visible_bookings(request.user)
    status_filter = request.GET.get('status')
    hostel_filter = request.GET.get('hostel') if request.user.role == 'SUPER_ADMIN' else None
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    q = request.GET.get('q', '')
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    if hostel_filter:
        bookings = bookings.filter(room__hostel_id=hostel_filter)
    if date_from:
        bookings = bookings.filter(check_in__gte=date_from)
    if date_to:
        bookings = bookings.filter(check_out__lte=date_to)
    if q:
        bookings = bookings.filter(
            Q(booking_reference__icontains=q) |
            Q(user__full_name__icontains=q) |
            Q(user__email__icontains=q)
        )
    hostels = access.visible_hostels(request.user).filter(is_active=True)
    bookings = bookings.order_by('-created_at')
    paginator = Paginator(bookings, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'bookings/booking_list.html', {
        'page_obj': page_obj,
        'hostels': hostels,
        'selected_status': status_filter,
        'selected_hostel': hostel_filter,
        'date_from': date_from, 'date_to': date_to, 'query': q,
    })


def _scoped_booking_or_404(request, pk):
    """Manager sees only their hostel's bookings; admin sees all."""
    return get_object_or_404(
        access.visible_bookings(request.user).select_related('user', 'bed', 'room', 'room__hostel'),
        pk=pk,
    )


@login_required
@manager_required
def confirm_booking(request, pk):
    booking = _scoped_booking_or_404(request, pk)
    if booking.status != 'pending':
        messages.error(request, 'Only pending bookings can be approved.')
        return redirect('booking_detail', pk=booking.pk)
    if request.method == 'POST':
        if booking.payment_status != 'paid':
            messages.warning(request, f'Booking {booking.booking_reference} has not been fully paid (status: {booking.payment_status}). Approving anyway.')
        booking.status = 'confirmed'
        booking.save()
        if booking.bed:
            booking.bed.refresh_status()
            booking.room.refresh_status()
        messages.success(request, f'Booking {booking.booking_reference} approved.')
        return redirect('booking_detail', pk=booking.pk)
    return render(request, 'bookings/booking_detail.html', {'booking': booking, 'action': 'confirm'})


@login_required
@manager_required
def reject_booking(request, pk):
    booking = _scoped_booking_or_404(request, pk)
    if booking.status != 'pending':
        messages.error(request, 'Only pending bookings can be rejected.')
        return redirect('booking_detail', pk=booking.pk)
    if request.method == 'POST':
        booking.status = 'rejected'
        booking.allocation_reason = (
            (booking.allocation_reason + '\n' if booking.allocation_reason else '') +
            f'Rejected by {request.user.full_name}: {request.POST.get("reason", "No reason provided.")}'
        )
        booking.save()
        _release_booking_resources(booking)
        messages.success(request, f'Booking {booking.booking_reference} rejected.')
        return redirect('booking_detail', pk=booking.pk)
    return render(request, 'bookings/booking_detail.html', {'booking': booking, 'action': 'reject'})


@login_required
@manager_required
def check_in_booking(request, pk):
    booking = _scoped_booking_or_404(request, pk)
    if booking.status != 'confirmed':
        messages.error(request, 'Only approved bookings can be checked in.')
        return redirect('booking_detail', pk=booking.pk)
    if request.method == 'POST':
        booking.status = 'checked_in'
        booking.save()
        if booking.bed:
            booking.bed.refresh_status()
        booking.room.refresh_status()
        _ensure_preferences(booking)
        messages.success(request, f'{booking.user.full_name} has checked in.')
        return redirect('booking_detail', pk=booking.pk)
    return render(request, 'bookings/booking_detail.html', {'booking': booking, 'action': 'check in'})


@login_required
@manager_required
def update_booking_status(request, pk):
    booking = _scoped_booking_or_404(request, pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Booking.STATUS_CHOICES):
            old_status = booking.status
            booking.status = new_status
            booking.save()
            if old_status == 'checked_in' and new_status != 'checked_in':
                _release_booking_resources(booking)
            elif new_status in ('confirmed', 'checked_in') and booking.bed:
                booking.bed.refresh_status()
                booking.room.refresh_status()
            messages.success(request, f'Booking status updated to {booking.get_status_display()}.')
        else:
            messages.error(request, 'Invalid status.')
    return redirect('booking_detail', pk=pk)


@login_required
@admin_required
def edit_booking(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('room'), pk=pk)
    if request.method == 'POST':
        form = BookingForm(request.POST, instance=booking)
        if form.is_valid():
            form.save()
            messages.success(request, f'Booking {booking.booking_reference} updated.')
            return redirect('booking_detail', pk=pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingForm(instance=booking)
    return render(request, 'bookings/booking_form.html', {'form': form, 'booking': booking})


@login_required
@manager_required
def check_out_booking(request, pk):
    booking = _scoped_booking_or_404(request, pk)
    if booking.status != 'checked_in':
        messages.error(request, 'Only checked-in bookings can be checked out.')
        return redirect('booking_detail', pk=booking.pk)
    if request.method == 'POST':
        booking.status = 'checked_out'
        booking.check_out = timezone.now().date()
        booking.save()
        _release_booking_resources(booking)
        messages.success(request, f'{booking.user.full_name} has checked out.')
        return redirect('booking_detail', pk=booking.pk)
    return render(request, 'bookings/booking_detail.html', {'booking': booking, 'action': 'check out'})


# ============================================================
# 7. PAYMENT VIEWS
# ============================================================

@login_required
def initiate_payment(request, booking_id):
    booking = get_object_or_404(access.visible_bookings(request.user), pk=booking_id)
    if request.user.role == 'RENTER' and booking.user != request.user:
        messages.error(request, 'You do not have permission to make payments for this booking.')
        return redirect('dashboard_home')
    if booking.payment_status == 'paid':
        messages.warning(request, 'This booking is already paid.')
        return redirect('booking_detail', pk=booking.pk)

    if booking.payment_status == 'pending_cod':
        messages.info(request, 'This booking is pending Cash on Delivery payment. Please pay the amount during check-in.')
        return redirect('booking_detail', pk=booking.pk)

    if request.method == 'GET':
        return render(request, 'payments/payment_checkout.html', {'booking': booking})

    existing = Payment.objects.filter(booking=booking, status__in=['pending', 'processing']).first()
    if existing:
        messages.info(request, 'A payment is already being processed for this booking.')
        gateway_url = (existing.metadata or {}).get('GatewayPageURL')
        if existing.status == 'processing' and gateway_url:
            return redirect(gateway_url)
        return redirect('booking_detail', pk=booking.pk)

    payment_method = request.POST.get('payment_method', 'sslcommerz')

    if payment_method == 'cod':
        # Handle Cash on Delivery
        return process_cod_payment(request, booking)

    # SSLCommerz Online Payment
    transaction_id = generate_transaction_id()
    payment = Payment.objects.create(
        booking=booking,
        user=booking.user,
        transaction_id=transaction_id,
        amount=booking.total_amount,
        status='pending',
        payment_method='sslcommerz',
    )

    ssl_data = {
        'store_id': settings.SSL_COMMERZ_STORE_ID,
        'store_passwd': settings.SSL_COMMERZ_STORE_PASSWORD,
        'total_amount': str(booking.total_amount),
        'currency': 'BDT',
        'tran_id': transaction_id,
        'success_url': request.build_absolute_uri(reverse('payment_success')),
        'fail_url': request.build_absolute_uri(reverse('payment_fail')),
        'cancel_url': request.build_absolute_uri(reverse('my_bookings')),
        'ipn_url': request.build_absolute_uri(reverse('ssl_ipn')),
        'emi_allow': 0,
        'cus_name': booking.user.full_name,
        'cus_email': booking.user.email,
        'cus_phone': booking.user.phone or '00000000000',
        'cus_add1': booking.room.hostel.address,
        'cus_country': 'Bangladesh',
        'shipping_method': 'NO',
        'product_name': f'Hostel Booking {booking.booking_reference}',
        'product_category': 'hostel',
        'product_profile': 'general',
    }

    try:
        response = requests.post(settings.SSLCOMMERZ_API_URL, data=ssl_data)
        result = response.json()
        if result.get('status') == 'SUCCESS':
            payment.status = 'processing'
            payment.metadata = {'GatewayPageURL': result.get('GatewayPageURL')}
            payment.save()
            return redirect(result['GatewayPageURL'])
        else:
            payment.status = 'failed'
            payment.metadata = result
            payment.save()
            messages.error(request, 'Payment initiation failed. Please try again.')
            return redirect('booking_detail', pk=booking.pk)
    except Exception:
        payment.status = 'failed'
        payment.metadata = {'error': 'Gateway connection failed'}
        payment.save()
        messages.error(request, 'Payment gateway error. Please try again.')
        return redirect('booking_detail', pk=booking.pk)


def process_cod_payment(request, booking):
    """Process Cash on Delivery payment - creates booking with COD payment status."""
    with transaction.atomic():
        # Check if there's already a pending payment for this booking
        existing = Payment.objects.filter(booking=booking, status__in=['pending', 'processing']).first()
        if existing:
            messages.info(request, 'A payment is already being processed for this booking.')
            return redirect('booking_detail', pk=booking.pk)

        # Create COD payment record
        payment = Payment.objects.create(
            booking=booking,
            user=booking.user,
            amount=booking.total_amount,
            status='pending',
            payment_method='cod',
        )

        # For COD, booking remains pending until manager verifies payment
        # Set payment status to 'pending_cod'
        booking.payment_status = 'pending_cod'
        booking.status = 'pending'
        booking.save()

        # Create a notification/message for the renter
        messages.success(request, 'Your booking is confirmed. Please pay during check-in.')
        return redirect('booking_detail', pk=booking.pk)


@login_required
@manager_required
def mark_cod_paid(request, payment_id):
    """Manager marks a COD payment as paid/verified."""
    if request.method != 'POST':
        return redirect('payment_history')
    
    payment = get_object_or_404(
        access.visible_payments(request.user).select_related('booking', 'booking__room', 'booking__user'),
        pk=payment_id,
        payment_method='cod'
    )
    
    if payment.status == 'success':
        messages.info(request, 'This payment has already been marked as paid.')
        return redirect('payment_history')
    
    # Mark payment as success
    payment.status = 'success'
    payment.payment_method = 'cod'
    payment.save()
    
    # Update booking payment status
    booking = payment.booking
    if booking:
        booking.payment_status = 'paid'
        booking.advance_paid = booking.total_amount
        if booking.status == 'pending':
            policy = booking.room.hostel.confirmation_policy
            if policy == 'AUTO':
                booking.status = 'confirmed'
        booking.save()
        booking.room.refresh_status()
        if booking.bed:
            booking.bed.refresh_status()
    
    messages.success(request, f'COD payment for booking {booking.booking_reference} marked as paid.')
    return redirect('payment_history')


def _mark_payment_success(payment, val_id):
    """Shared success handler for browser redirect and IPN."""
    payment.status = 'success'
    payment.validation_id = val_id
    payment.payment_method = 'sslcommerz'
    payment.save()

    booking = payment.booking
    if not booking:
        return

    if payment.payment_type == 'meal':
        # A meal payment may settle one daily bill (daily flow) or a whole calendar
        # month (monthly flow, tagged metadata['meal_month']). Mark every linked unpaid
        # bill, and for a monthly payment every unpaid bill of that month, as paid.
        month = (payment.metadata or {}).get('meal_month')
        if month:
            try:
                y, m = month.split('-')
                meal_bills = list(MealBill.objects.filter(
                    booking=booking, is_paid=False,
                    date__year=int(y), date__month=int(m),
                ).exclude(pk__in=MealBill.objects.filter(
                    booking=booking, payment=payment).values('pk')))
            except (ValueError, TypeError):
                meal_bills = []
        else:
            meal_bills = []
        linked = list(MealBill.objects.filter(booking=booking, payment=payment, is_paid=False))
        for meal_bill in list(linked) + meal_bills:
            meal_bill.is_paid = True
            meal_bill.payment = payment
            meal_bill.save(update_fields=['is_paid', 'payment', 'updated_at'])
            Notification.objects.create(
                user=booking.user,
                type='meal_paid',
                title='Meal Payment Successful',
                message=f'Your meal payment of ৳{meal_bill.total_amount} for {meal_bill.date.strftime("%B %d")} has been confirmed.',
                related_bill=meal_bill
            )
    else:
        # Room booking payment
        booking.payment_status = 'paid'
        booking.advance_paid = booking.total_amount
        if booking.status == 'pending':
            policy = booking.room.hostel.confirmation_policy
            if policy == 'AUTO':
                booking.status = 'confirmed'
        booking.save()
        booking.room.refresh_status()


@csrf_exempt
def payment_success(request):
    if request.method == 'POST':
        transaction_id = request.POST.get('tran_id')
        val_id = request.POST.get('val_id')

        try:
            payment = Payment.objects.select_related('booking__room__hostel').get(transaction_id=transaction_id)
        except Payment.DoesNotExist:
            messages.error(request, 'Invalid transaction.')
            return redirect('dashboard_home')

        verify_url = settings.SSLCOMMERZ_VALIDATOR_URL
        verify_params = {
            'val_id': val_id,
            'store_id': settings.SSL_COMMERZ_STORE_ID,
            'store_passwd': settings.SSL_COMMERZ_STORE_PASSWORD,
            'format': 'json',
        }
        try:
            verify_response = requests.get(verify_url, params=verify_params)
            verify_result = verify_response.json()
            if verify_result.get('status') == 'VALID' or settings.DEBUG:
                _mark_payment_success(payment, val_id)
                messages.success(request, 'Payment successful!')
                return redirect('payment_receipt', transaction_id=transaction_id)
        except Exception:
            pass

    messages.error(request, 'Payment verification failed.')
    return redirect('dashboard_home')


@csrf_exempt
def payment_fail(request):
    if request.method == 'POST':
        transaction_id = request.POST.get('tran_id')
        try:
            payment = Payment.objects.get(transaction_id=transaction_id)
            payment.status = 'failed'
            payment.metadata = dict(request.POST)
            payment.save()
        except Payment.DoesNotExist:
            pass
    messages.error(request, 'Payment was cancelled or failed.')
    return redirect('my_bookings')


@csrf_exempt
def ssl_ipn(request):
    if request.method == 'POST':
        transaction_id = request.POST.get('tran_id')
        val_id = request.POST.get('val_id')

        try:
            payment = Payment.objects.select_related('booking__room__hostel').get(transaction_id=transaction_id)
        except Payment.DoesNotExist:
            return HttpResponse('IPN Received')

        verify_url = settings.SSLCOMMERZ_VALIDATOR_URL
        verify_params = {
            'val_id': val_id,
            'store_id': settings.SSL_COMMERZ_STORE_ID,
            'store_passwd': settings.SSL_COMMERZ_STORE_PASSWORD,
            'format': 'json',
        }
        try:
            verify_response = requests.get(verify_url, params=verify_params)
            verify_result = verify_response.json()
            if verify_result.get('status') == 'VALID':
                _mark_payment_success(payment, val_id)
        except Exception:
            pass

    return HttpResponse('IPN Received')


@login_required
def payment_history(request):
    payments = access.visible_payments(request.user).select_related('booking__room__hostel', 'user')
    status_filter = request.GET.get('status')
    method_filter = request.GET.get('method')
    type_filter = request.GET.get('type')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    q = request.GET.get('q', '')
    if status_filter:
        payments = payments.filter(status=status_filter)
    if method_filter in ('sslcommerz', 'cod'):
        payments = payments.filter(payment_method=method_filter)
    if type_filter in ('room', 'meal'):
        payments = payments.filter(payment_type=type_filter)
    if date_from:
        payments = payments.filter(payment_date__date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__date__lte=date_to)
    if q:
        payments = payments.filter(
            Q(transaction_id__icontains=q) |
            Q(user__full_name__icontains=q) |
            Q(user__email__icontains=q)
        )
    payments = payments.order_by('-payment_date')
    paginator = Paginator(payments, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'payments/payment_history.html', {
        'page_obj': page_obj,
        'selected_status': status_filter,
        'selected_method': method_filter,
        'selected_type': type_filter,
        'date_from': date_from, 'date_to': date_to,
        'query': q,
        'is_paginated': page_obj.has_other_pages(),
    })


@login_required
def payment_receipt(request, transaction_id):
    payment = get_object_or_404(
        access.visible_payments(request.user).select_related('booking__room__hostel', 'user'),
        transaction_id=transaction_id,
    )
    return render(request, 'payments/payment_receipt.html', {'payment': payment})


@login_required
def payment_receipt_detail(request, payment_id):
    """Dedicated receipt detail page."""
    payment = get_object_or_404(
        access.visible_payments(request.user).select_related(
            'booking__room__hostel', 'booking__room__unit__floor', 'user', 'booking__bed'
        ),
        pk=payment_id,
    )
    total_paid = 0
    if payment.booking:
        total_paid = (payment.booking.total_amount or 0) + (payment.booking.room.security_deposit or 0)
    return render(request, 'payments/receipt_detail.html', {'payment': payment, 'total_paid': total_paid})


@login_required
def payment_receipt_download(request, payment_id):
    """Download PDF receipt."""
    payment = get_object_or_404(
        access.visible_payments(request.user).select_related(
            'booking__room__hostel', 'booking__room__unit__floor', 'user', 'booking__bed'
        ),
        pk=payment_id,
    )
    # Generate PDF
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, 
                           topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = styles['Title']
    heading_style = styles['Heading1']
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8)
    
    receipt_title_style = ParagraphStyle(
        'ReceiptTitle',
        parent=styles['Title'],
        fontSize=20,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    
    receipt_heading_style = ParagraphStyle(
        'ReceiptHeading',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=2,
        textColor=colors.HexColor('#2c3e50'),
    )
    
    label_style = ParagraphStyle(
        'ReceiptLabel',
        parent=normal,
        fontSize=9,
        fontName='Helvetica-Bold',
    )
    
    value_style = ParagraphStyle(
        'ReceiptValue',
        parent=normal,
        fontSize=9,
        fontName='Helvetica',
    )
    
    # Build story
    story = []
    
    # Header
    story.append(Paragraph('TOUCH AND SOLVE (TNS)', receipt_title_style))
    story.append(Paragraph('Smart Living. Smarter Management.', ParagraphStyle(
        'SubTitle', parent=normal, fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor('#7f8c8d')
    )))
    story.append(Spacer(1, 4*mm))
    
    # Receipt heading
    story.append(Paragraph('PAYMENT RECEIPT', receipt_heading_style))
    story.append(Spacer(1, 4*mm))
    
    # Receipt Information table
    story.append(Paragraph('Receipt Information', ParagraphStyle(
        'SectionHeading', parent=normal, fontSize=10, fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=2
    )))
    
    booking_ref = payment.booking.booking_reference if payment.booking else 'N/A'
    receipt_data = [
        ['Receipt No:', payment.transaction_id],
        ['Transaction ID:', payment.transaction_id],
        ['Booking Reference:', booking_ref],
        ['Payment Date:', payment.payment_date.strftime('%d/%m/%Y') if payment.payment_date else 'N/A'],
        ['Payment Status:', 'PAID'],
    ]
    
    receipt_table = Table(receipt_data, colWidths=[60*mm, 100*mm])
    receipt_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(receipt_table)
    story.append(Spacer(1, 4*mm))
    
    # Renter Information
    story.append(Paragraph('Renter Information', ParagraphStyle(
        'SectionHeading2', parent=normal, fontSize=10, fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=2
    )))
    
    if payment.booking:
        renter_name = payment.booking.user.full_name
        renter_email = payment.booking.user.email
        renter_phone = payment.booking.user.phone or 'N/A'
    else:
        renter_name = payment.user.full_name
        renter_email = payment.user.email
        renter_phone = payment.user.phone or 'N/A'
    renter_data = [
        ['Name:', renter_name],
        ['Email:', renter_email],
        ['Phone:', renter_phone],
    ]
    
    renter_table = Table(renter_data, colWidths=[60*mm, 100*mm])
    renter_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(renter_table)
    story.append(Spacer(1, 4*mm))
    
    # Accommodation
    story.append(Paragraph('Accommodation', ParagraphStyle(
        'SectionHeading3', parent=normal, fontSize=10, fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=2
    )))
    
    if payment.booking:
        hostel_name = payment.booking.room.hostel.name
        floor_name = str(payment.booking.room.unit.floor.display_name or 'N/A')
        unit_name = payment.booking.room.unit.name
        room_number = payment.booking.room.room_number
        bed_number = payment.bed.bed_number if payment.bed else 'N/A'
    else:
        hostel_name = 'N/A'
        floor_name = 'N/A'
        unit_name = 'N/A'
        room_number = 'N/A'
        bed_number = 'N/A'
    acc_data = [
        ['Hostel:', hostel_name],
        ['Floor:', floor_name],
        ['Unit:', unit_name],
        ['Room:', room_number],
        ['Bed:', bed_number],
    ]
    
    acc_table = Table(acc_data, colWidths=[60*mm, 100*mm])
    acc_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(acc_table)
    story.append(Spacer(1, 4*mm))
    
    # Payment Details
    story.append(Paragraph('Payment Details', ParagraphStyle(
        'SectionHeading4', parent=normal, fontSize=10, fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=2
    )))
    
    # Calculate amounts (with None checks)
    meal_charge = 0
    if payment.booking:
        booking_rent = payment.booking.total_amount or 0
        security_deposit = payment.booking.room.security_deposit or 0
        # Check for meal preferences
        from .models import MealPreference, MealBill
        meal_bills = MealBill.objects.filter(booking=payment.booking)
        if meal_bills.exists():
            for mb in meal_bills:
                if mb.month == timezone.now().strftime('%Y-%m'):
                    meal_charge = mb.total_amount or 0
                    break
    else:
        booking_rent = 0
        security_deposit = 0
    
    payment_data = [
        ['Booking Payment', f'৳ {booking_rent:,.0f}'],
        ['Security Deposit', f'৳ {security_deposit:,.0f}'],
        ['Meal Charge', f'৳ {meal_charge:,.0f}'],
    ]
    
    # Add total
    total = booking_rent + security_deposit + meal_charge
    payment_data.append(['TOTAL PAID', f'৳ {total:,.0f}'])
    
    # Reverse so total is on top? No, keep as is but format better
    # Actually let's format: description in first column, amount in second
    # But Table reads row by row. Let's transpose the logic.
    
    # Let me redo this properly
    # Columns: Description | Amount
    table_data = [['Description', 'Amount']]
    for desc, amount in payment_data:
        table_data.append([desc, amount])
    
    pay_table = Table(table_data, colWidths=[80*mm, 50*mm])
    pay_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ecf0f1')),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#bdc3c7')),
    ]))
    story.append(pay_table)
    story.append(Spacer(1, 4*mm))
    
    # Payment Method and Status
    story.append(Spacer(1, 4*mm))

    # Payment Method
    payment_method_text = 'Cash on Delivery' if payment.payment_method == 'cod' else 'SSLCommerz'
    payment_method_color = colors.HexColor('#27ae60') if payment.payment_method == 'cod' else colors.HexColor('#2c3e50')
    story.append(Paragraph(f'Payment Method: {payment_method_text}', ParagraphStyle(
        'PayMethod', parent=normal, fontSize=9, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=payment_method_color
    )))

    # Payment Status
    if payment.payment_method == 'cod' and payment.status != 'success':
        status_text = 'Status: Pending COD'
        status_color = colors.HexColor('#f39c12')
    else:
        status_text = 'Status: PAID'
        status_color = colors.HexColor('#27ae60')
    story.append(Paragraph(status_text, ParagraphStyle(
        'PayStatus', parent=normal, fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=status_color
    )))    
    # Footer
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph('Thank you for choosing Touch and Solve (TNS) Hostel.', ParagraphStyle(
        'Footer', parent=normal, fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor('#7f8c8d'))
    ))
    story.append(Paragraph('This is a computer-generated receipt.', ParagraphStyle(
        'Footer2', parent=normal, fontSize=7, alignment=TA_CENTER, textColor=colors.HexColor('#7f8c8d'))
    ))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Return as download
    filename = f'TNS_Payment_Receipt_{payment.transaction_id}.pdf'
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ============================================================
# 8. COMPLAINT VIEWS
# ============================================================

@login_required
def create_complaint(request):
    if request.method == 'POST':
        form = ComplaintForm(request.POST, user=request.user)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.user = request.user
            complaint.save()
            messages.success(request, 'Complaint submitted successfully.')
            return redirect('my_complaints')
    else:
        form = ComplaintForm(user=request.user)
    return render(request, 'complaints/complaint_form.html', {'form': form, 'title': 'Submit Complaint'})


@login_required
def my_complaints(request):
    complaints = Complaint.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'complaints/my_complaints.html', {'complaints': complaints})


@login_required
@manager_required
def complaint_list(request):
    complaints = access.visible_complaints(request.user).select_related('user', 'assigned_to', 'room', 'room__hostel')
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    q = request.GET.get('q', '')
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    if priority_filter:
        complaints = complaints.filter(priority=priority_filter)
    if q:
        complaints = complaints.filter(
            Q(subject__icontains=q) |
            Q(user__full_name__icontains=q)
        )
    return render(request, 'complaints/complaint_list.html', {
        'complaints': complaints.order_by('-created_at'),
        'selected_status': status_filter, 'selected_priority': priority_filter, 'query': q,
    })


@login_required
def complaint_detail(request, pk):
    complaint = get_object_or_404(
        access.visible_complaints(request.user).select_related('user', 'assigned_to', 'room'),
        pk=pk,
    )
    can_manage = request.user.role in ('SUPER_ADMIN', 'HOSTEL_MANAGER')
    staff = None
    if can_manage:
        hostel = complaint.room.hostel if complaint.room else None
        staff = User.objects.filter(role='HOSTEL_MANAGER')
        if hostel and request.user.role == 'SUPER_ADMIN':
            staff = User.objects.filter(Q(role='HOSTEL_MANAGER') | Q(pk=hostel.manager_id))
    return render(request, 'complaints/complaint_detail.html', {
        'complaint': complaint, 'can_manage': can_manage, 'staff': staff,
    })


@login_required
@manager_required
def assign_complaint(request, pk):
    complaint = get_object_or_404(access.visible_complaints(request.user), pk=pk)
    if request.method == 'POST':
        assigned_to_id = request.POST.get('assigned_to')
        if assigned_to_id:
            complaint.assigned_to_id = assigned_to_id
            complaint.status = 'in_progress'
            complaint.save()
            messages.success(request, 'Complaint assigned successfully.')
            return redirect('complaint_detail', pk=complaint.pk)
        messages.error(request, 'Please select a staff member to assign.')
    staff = User.objects.filter(role='HOSTEL_MANAGER', is_active=True)
    return render(request, 'complaints/complaint_detail.html', {'complaint': complaint, 'staff': staff})


@login_required
@manager_required
def resolve_complaint(request, pk):
    complaint = get_object_or_404(access.visible_complaints(request.user), pk=pk)
    if request.method == 'POST':
        complaint.status = 'resolved'
        complaint.admin_note = request.POST.get('admin_note', '')
        complaint.save()
        messages.success(request, 'Complaint marked as resolved.')
        return redirect('complaint_detail', pk=complaint.pk)
    return render(request, 'complaints/complaint_detail.html', {'complaint': complaint})

# ============================================================
# 9. MANAGER MANAGEMENT (SUPER ADMIN)
# ============================================================

@login_required
@admin_required
def manager_list(request):
    managers = User.objects.filter(role='HOSTEL_MANAGER').select_related('assigned_hostel').order_by('-date_joined')
    q = request.GET.get('q', '')
    status_filter = request.GET.get('status')
    if q:
        managers = managers.filter(
            Q(full_name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
    if status_filter == 'active':
        managers = managers.filter(is_active=True)
    elif status_filter == 'inactive':
        managers = managers.filter(is_active=False)
    elif status_filter == 'unassigned':
        managers = managers.filter(assigned_hostel__isnull=True)
    paginator = Paginator(managers, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'managers/manager_list.html', {
        'page_obj': page_obj, 'query': q, 'selected_status': status_filter,
    })


@login_required
@admin_required
def manager_add(request):
    if request.method == 'POST':
        form = ManagerCreateForm(request.POST)
        if form.is_valid():
            manager = form.save()
            messages.success(request, f'Manager {manager.full_name} created successfully.')
            return redirect('manager_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ManagerCreateForm()
    return render(request, 'managers/manager_form.html', {'form': form, 'title': 'Add Hostel Manager'})


@login_required
@admin_required
def manager_edit(request, pk):
    manager = get_object_or_404(User, pk=pk, role='HOSTEL_MANAGER')
    if request.method == 'POST':
        form = ManagerEditForm(request.POST, instance=manager)
        if form.is_valid():
            form.save()
            messages.success(request, f'Manager {manager.full_name} updated.')
            return redirect('manager_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ManagerEditForm(instance=manager)
    return render(request, 'managers/manager_form.html', {
        'form': form, 'title': f'Edit {manager.full_name}', 'manager': manager,
    })


@login_required
@admin_required
def manager_delete(request, pk):
    manager = get_object_or_404(User, pk=pk, role='HOSTEL_MANAGER')
    if request.method == 'POST':
        if hasattr(manager, 'assigned_hostel') and manager.assigned_hostel:
            messages.error(request, f'{manager.full_name} is assigned to {manager.assigned_hostel.name}. Unassign them first.')
            return redirect('manager_list')
        name = manager.full_name
        manager.is_active = False
        manager.save()
        messages.success(request, f'Manager {name} deactivated.')
        return redirect('manager_list')
    return render(request, 'managers/manager_confirm_delete.html', {'manager': manager})


# ============================================================
# 12. NOTICE VIEWS
# ============================================================

@login_required
def notice_list(request):
    notices = access.visible_notices(request.user).filter(is_active=True)
    return render(request, 'notices/notice_list.html', {'notices': notices})


@login_required
@manager_required
def notice_create(request):
    if request.method == 'POST':
        form = NoticeForm(request.POST, user=request.user)
        if form.is_valid():
            notice = form.save(commit=False)
            notice.created_by = request.user
            notice.save()
            messages.success(request, 'Notice published successfully.')
            return redirect('notice_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = NoticeForm(user=request.user)
    return render(request, 'notices/notice_form.html', {'form': form, 'title': 'Create Notice'})


@login_required
@manager_required
def notice_edit(request, pk):
    notice = get_object_or_404(access.visible_notices(request.user), pk=pk)
    if request.method == 'POST':
        form = NoticeForm(request.POST, instance=notice, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Notice updated successfully.')
            return redirect('notice_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = NoticeForm(instance=notice, user=request.user)
    return render(request, 'notices/notice_form.html', {'form': form, 'notice': notice, 'title': 'Edit Notice'})


@login_required
@manager_required
def notice_delete(request, pk):
    notice = get_object_or_404(access.visible_notices(request.user), pk=pk)
    if request.method == 'POST':
        notice.delete()
        messages.success(request, 'Notice deleted successfully.')
        return redirect('notice_list')
    return render(request, 'notices/notice_confirm_delete.html', {'notice': notice})


# ============================================================
# 13. VISITOR VIEWS
# ============================================================

@login_required
@manager_required
def visitor_list(request):
    visitors = access.visible_visitors(request.user).select_related('host', 'room').order_by('-entry_time')
    q = request.GET.get('q', '')
    inside_filter = request.GET.get('inside')
    if q:
        visitors = visitors.filter(
            Q(name__icontains=q) |
            Q(host__full_name__icontains=q)
        )
    if inside_filter == 'yes':
        visitors = visitors.filter(is_inside=True)
    elif inside_filter == 'no':
        visitors = visitors.filter(is_inside=False)
    return render(request, 'visitors/visitor_list.html', {
        'visitors': visitors, 'query': q, 'selected_inside': inside_filter,
    })


@login_required
@manager_required
def visitor_entry(request):
    hostel = access.require_manager_hostel(request.user)
    if request.method == 'POST':
        form = VisitorForm(request.POST)
        if form.is_valid():
            visitor = form.save(commit=False)
            visitor.hostel = hostel
            host_id = request.POST.get('host')
            room_id = request.POST.get('room')
            if host_id:
                visitor.host_id = host_id
            if room_id:
                visitor.room_id = room_id
            visitor.save()
            messages.success(request, 'Visitor entry recorded.')
            return redirect('visitor_list')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = VisitorForm()
    renters = User.objects.filter(
        role='RENTER', is_active=True,
        bookings__room__hostel=hostel,
        bookings__status='checked_in',
    ).distinct()
    rooms = access.visible_rooms(request.user).filter(is_active=True)
    return render(request, 'visitors/visitor_form.html', {
        'form': form, 'renters': renters, 'rooms': rooms,
    })


@login_required
@manager_required
def visitor_exit(request, pk):
    visitor = get_object_or_404(access.visible_visitors(request.user), pk=pk)
    if request.method == 'POST':
        visitor.exit_time = timezone.now()
        visitor.is_inside = False
        visitor.save()
        messages.success(request, f'{visitor.name} has been checked out.')
        return redirect('visitor_list')
    return render(request, 'visitors/visitor_list.html', {'visitor': visitor})


def override_allocation(booking, new_room, manager, justification):
    """Manager override: move a booking to any room with a free bed for the dates."""
    from .models import Bed

    old_room = booking.room
    old_bed = booking.bed

    with transaction.atomic():
        locked_room = type(new_room).objects.select_for_update().get(pk=new_room.pk)

        candidate_beds = list(
            Bed.objects.filter(room=locked_room, is_active=True, status='available')
            .select_for_update()
            .order_by('id')
        )
        target_bed = None
        for bed in candidate_beds:
            overlap = bed.bookings.filter(
                status__in=['pending', 'confirmed', 'checked_in'],
                check_in__lt=booking.check_out,
                check_out__gt=booking.check_in,
            ).exclude(pk=booking.pk).exists()
            if not overlap:
                target_bed = bed
                break

        if not target_bed:
            return False, 'Target room has no free bed for these dates.'

        booking.room = locked_room
        booking.bed = target_bed
        booking.allocation_method = 'manager_override'
        booking.allocation_reason = f'Manager override by {manager.full_name}: {justification}'
        booking.save()

        locked_room.refresh_status()
        if old_room and old_room.pk != locked_room.pk:
            old_room.refresh_status()

        return True, f'Booking reassigned to room {locked_room.room_number}, bed {target_bed.bed_number}.'


# ============================================================
# 13.5 ALLOCATION POLICY VIEWS
# ============================================================

@login_required
@manager_required
def manager_override_allocation(request, pk):
    booking = get_object_or_404(
        access.visible_bookings(request.user).select_related('room__hostel', 'user'),
        pk=pk,
    )
    if booking.status not in ('pending', 'confirmed'):
        messages.error(request, 'Only pending or confirmed bookings can be reassigned.')
        return redirect('booking_detail', pk=pk)

    if request.method == 'POST':
        form = AllocationOverrideForm(request.POST, user=request.user)
        if form.is_valid():
            new_room = form.cleaned_data['new_room']
            justification = form.cleaned_data['justification']
            success, msg = override_allocation(booking, new_room, request.user, justification)
            if success:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect('booking_detail', pk=pk)
        messages.error(request, 'Please correct the errors below.')
    else:
        form = AllocationOverrideForm(user=request.user)

    return render(request, 'bookings/override_allocation.html', {
        'booking': booking, 'form': form,
    })





# ============================================================
# 14. DASHBOARD VIEWS
# ============================================================

@login_required
def dashboard_home(request):
    role_map = {
        'SUPER_ADMIN': 'super_admin_dashboard',
        'HOSTEL_MANAGER': 'manager_dashboard',
        'RENTER': 'renter_dashboard',
    }
    return redirect(role_map.get(request.user.role, 'renter_dashboard'))


def _get_admin_stats():
    today = date.today()
    first_of_month = today.replace(day=1)

    total_hostels = Hostel.objects.count()
    total_rooms = Room.objects.count()
    total_beds = Bed.objects.filter(is_active=True).count()
    occupied_beds = Bed.objects.filter(is_active=True, status='occupied').count()
    available_beds = Bed.objects.filter(is_active=True, status='available').count()
    maintenance_beds = Bed.objects.filter(is_active=True, status='maintenance').count()
    available_rooms = Room.objects.filter(status='available').count()
    occupied_rooms = Room.objects.filter(status='occupied').count()
    booked_rooms = Room.objects.filter(status='booked').count()
    total_bookings = Booking.objects.count()
    pending_bookings = Booking.objects.filter(status='pending').count()
    total_renters = User.objects.filter(role='RENTER').count()
    total_managers = User.objects.filter(role='HOSTEL_MANAGER').count()
    total_complaints = Complaint.objects.count()

    total_revenue = Payment.objects.filter(
        status='success',
    ).aggregate(total=Sum('amount'))['total'] or 0

    monthly_revenue = Payment.objects.filter(
        status='success',
        payment_date__gte=first_of_month,
    ).aggregate(total=Sum('amount'))['total'] or 0

    today_collection = Payment.objects.filter(
        status='success',
        payment_date__date=today,
    ).aggregate(total=Sum('amount'))['total'] or 0

    recent_bookings = Booking.objects.select_related('user', 'bed', 'room__hostel').order_by('-created_at')[:10]

    revenue_by_month = list(
        Payment.objects.filter(status='success')
        .extra(select={'month': "strftime('%%Y-%%m', payment_date)"})
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )

    booking_by_month = list(
        Booking.objects
        .extra(select={'month': "strftime('%%Y-%%m', created_at)"})
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    occupancy_data = {
        'available': available_rooms,
        'booked': booked_rooms,
        'occupied': occupied_rooms,
        'maintenance': Room.objects.filter(status='maintenance').count(),
    }

    return {
        'total_hostels': total_hostels,
        'total_rooms': total_rooms,
        'total_beds': total_beds,
        'occupied_beds': occupied_beds,
        'available_beds': available_beds,
        'maintenance_beds': maintenance_beds,
        'total_managers': total_managers,
        'total_bookings': total_bookings,
        'available_rooms': available_rooms,
        'occupied_rooms': occupied_rooms,
        'pending_bookings': pending_bookings,
        'total_renters': total_renters,
        'monthly_revenue': monthly_revenue,
        'today_collection': today_collection,
        'total_complaints': total_complaints,
        'total_revenue': total_revenue,
        'recent_bookings': recent_bookings,
        'revenue_by_month': revenue_by_month,
        'booking_by_month': booking_by_month,
        'occupancy_data': occupancy_data,
    }


@login_required
@admin_required
def super_admin_dashboard(request):
    return render(request, 'dashboard/super_admin_dashboard.html', _get_admin_stats())


@login_required
@admin_required
def admin_dashboard(request):
    return render(request, 'dashboard/admin_dashboard.html', _get_admin_stats())


@login_required
@manager_required
def manager_dashboard(request):
    hostel = access.get_manager_hostel(request.user)
    if not hostel:
        return render(request, 'dashboard/manager_dashboard.html', {
            'hostel': None,
        })
    today = date.today()
    rooms = access.visible_rooms(request.user)
    bookings = access.visible_bookings(request.user)
    payments = access.visible_payments(request.user)
    complaints = access.visible_complaints(request.user)

    total_rooms = rooms.count()
    available_rooms = rooms.filter(status='available').count()
    occupied_rooms = rooms.filter(status='occupied').count()
    total_beds = Bed.objects.filter(room__hostel=hostel, is_active=True).count()
    occupied_beds = Bed.objects.filter(room__hostel=hostel, is_active=True, status='occupied').count()
    total_bookings = bookings.count()
    pending_bookings = bookings.filter(status='pending').count()
    pending_approvals = bookings.filter(status='pending', payment_status='paid').count()
    active_tenants = bookings.filter(status='checked_in').count()
    checked_out_today = bookings.filter(status='checked_out', check_out=today).count()
    total_revenue = payments.filter(status='success').aggregate(total=Sum('amount'))['total'] or 0
    today_collection = payments.filter(
        status='success',
        payment_date__date=today,
    ).aggregate(total=Sum('amount'))['total'] or 0
    pending_complaints = complaints.filter(status='pending').count()
    recent_bookings = bookings.select_related('user', 'bed', 'room').order_by('-created_at')[:10]
    inside_visitors = Visitor.objects.filter(hostel=hostel, is_inside=True).count()
    return render(request, 'dashboard/manager_dashboard.html', {
        'hostel': hostel,
        'total_rooms': total_rooms,
        'available_rooms': available_rooms,
        'occupied_rooms': occupied_rooms,
        'total_beds': total_beds,
        'occupied_beds': occupied_beds,
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'pending_approvals': pending_approvals,
        'active_tenants': active_tenants,
        'checked_out_today': checked_out_today,
        'total_revenue': total_revenue,
        'today_collection': today_collection,
        'recent_bookings': recent_bookings,
        'pending_complaints': pending_complaints,
        'inside_visitors': inside_visitors,
    })


@login_required
@renter_required
def renter_dashboard(request):
    user = request.user
    bookings = Booking.objects.filter(user=user).select_related('bed', 'room__hostel').order_by('-created_at')[:5]
    payments = Payment.objects.filter(user=user).select_related('booking').order_by('-payment_date')[:10]
    complaints = Complaint.objects.filter(user=user).order_by('-created_at')[:5]
    active_booking = Booking.objects.filter(
        user=user,
        status__in=['confirmed', 'checked_in'],
        bed__isnull=False,
    ).select_related('bed', 'room__hostel').order_by('-created_at').first()
    meal_bills = MealBill.objects.filter(booking__user=user).select_related('booking').order_by('-created_at')[:5]
    return render(request, 'dashboard/renter_dashboard.html', {
        'bookings': bookings,
        'payments': payments,
        'complaints': complaints,
        'active_booking': active_booking,
        'meal_bills': meal_bills,
        'total_bookings': Booking.objects.filter(user=user).count(),
        'active_bookings': Booking.objects.filter(user=user, status='confirmed').count(),
        'payments_made': Payment.objects.filter(user=user, status='success').count(),
        'pending_complaints': Complaint.objects.filter(user=user, status='pending').count(),
    })


# ============================================================
# 15. REPORT VIEWS
# ============================================================

@login_required
@manager_required
def report_index(request):
    return render(request, 'reports/report_index.html')


@login_required
@manager_required
def booking_report(request):
    start_date = request.GET.get('from') or request.GET.get('start_date')
    end_date = request.GET.get('to') or request.GET.get('end_date')
    status_filter = request.GET.get('status')
    bookings = access.visible_bookings(request.user).select_related('user', 'bed', 'room__hostel')
    if start_date:
        bookings = bookings.filter(created_at__gte=start_date)
    if end_date:
        bookings = bookings.filter(created_at__lte=end_date)
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    total_bookings = bookings.count()
    total_revenue = bookings.aggregate(total=Sum('total_amount'))['total'] or 0
    return render(request, 'reports/booking_report.html', {
        'bookings': bookings, 'total_bookings': total_bookings,
        'total_revenue': total_revenue, 'start_date': start_date, 'end_date': end_date,
    })


@login_required
@manager_required
def payment_report(request):
    start_date = request.GET.get('from') or request.GET.get('start_date')
    end_date = request.GET.get('to') or request.GET.get('end_date')
    status_filter = request.GET.get('status')
    type_filter = request.GET.get('type')
    payments = access.visible_payments(request.user).filter(status='success').select_related('user', 'booking')
    if start_date:
        payments = payments.filter(payment_date__gte=start_date)
    if end_date:
        payments = payments.filter(payment_date__lte=end_date)
    if status_filter:
        payments = payments.filter(status=status_filter)
    if type_filter in ('room', 'meal'):
        payments = payments.filter(payment_type=type_filter)
    
    room_payments = payments.filter(payment_type='room')
    meal_payments = payments.filter(payment_type='meal')
    
    total_amount = payments.aggregate(total=Sum('amount'))['total'] or 0
    total_count = payments.count()
    by_method = payments.values('payment_method').annotate(total=Sum('amount'), count=Count('id')).order_by('-total')
    by_type = payments.values('payment_type').annotate(total=Sum('amount'), count=Count('id')).order_by('-total')
    
    return render(request, 'reports/payment_report.html', {
        'payments': payments, 'total_amount': total_amount,
        'total_count': total_count, 'by_method': by_method,
        'by_type': by_type,
        'room_payments': room_payments, 'meal_payments': meal_payments,
        'start_date': start_date, 'end_date': end_date,
        'selected_type': type_filter,
    })


@login_required
@manager_required
def room_report(request):
    rooms = access.visible_rooms(request.user).select_related('hostel', 'room_type')
    total = rooms.count()
    available = rooms.filter(status='available').count()
    booked = rooms.filter(status='booked').count()
    occupied = rooms.filter(status='occupied').count()
    maintenance = rooms.filter(status='maintenance').count()
    by_hostel = rooms.values('hostel__name').annotate(
        total=Count('id'),
        available_count=Count('id', filter=Q(status='available')),
    ).order_by('-total')
    return render(request, 'reports/room_report.html', {
        'rooms': rooms, 'total_rooms': total, 'available_count': available,
        'booked_count': booked, 'occupied_count': occupied,
        'maintenance_count': maintenance, 'by_hostel': by_hostel,
    })


@login_required
@manager_required
def complaint_report(request):
    category = request.GET.get('category')
    status_filter = request.GET.get('status')
    complaints = access.visible_complaints(request.user).select_related('user', 'assigned_to', 'room')
    if category:
        complaints = complaints.filter(category=category)
    if status_filter:
        complaints = complaints.filter(status=status_filter)
    by_category = complaints.values('category').annotate(count=Count('id')).order_by('category')
    by_status = complaints.values('status').annotate(count=Count('id')).order_by('status')
    return render(request, 'reports/complaint_report.html', {
        'complaints': complaints, 'by_category': by_category,
        'by_status': by_status, 'total_count': complaints.count(),
        'pending_count': complaints.filter(status='pending').count(),
        'in_progress_count': complaints.filter(status='in_progress').count(),
        'resolved_count': complaints.filter(status='resolved').count(),
        'category': category, 'status_filter': status_filter,
    })


@login_required
@manager_required
def revenue_report(request):
    year = request.GET.get('year', str(date.today().year))
    payments = access.visible_payments(request.user).filter(status='success', payment_date__year=year)

    monthly = list(
        payments.extra(select={'month': "strftime('%%m', payment_date)"})
        .values('month')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('month')
    )

    monthly_map = {m['month']: m for m in monthly}
    month_names = []
    month_totals = []
    month_counts = []
    for i in range(1, 13):
        key = f'{i:02d}'
        m = monthly_map.get(key, {})
        month_names.append(calendar.month_name[i])
        month_totals.append(float(m.get('total', 0)))
        month_counts.append(m.get('count', 0))

    grand_total = sum(month_totals)
    total_revenue = grand_total
    total_count = payments.count()
    payment_methods_count = payments.values('payment_method').distinct().count()

    all_payments = payments.select_related('user', 'booking')

    return render(request, 'reports/revenue_report.html', {
        'month_names': json.dumps(month_names), 'month_totals': json.dumps(month_totals),
        'month_counts': json.dumps(month_counts), 'grand_total': grand_total, 'year': year,
        'total_revenue': total_revenue, 'total_count': total_count,
        'payment_methods_count': payment_methods_count, 'payments': all_payments,
    })


@login_required
@manager_required
def export_pdf(request, report_type):
    start_date = request.GET.get('start_date') or request.GET.get('from')
    end_date = request.GET.get('end_date') or request.GET.get('to')
    year = request.GET.get('year', str(date.today().year))
    context = {'report_type': report_type, 'generated_at': timezone.now(), 'title': f'{report_type.title()} Report'}
    if start_date:
        context['start_date'] = start_date
    if end_date:
        context['end_date'] = end_date

    if report_type == 'bookings':
        data = access.visible_bookings(request.user).select_related('user', 'bed', 'room__hostel')
        if start_date:
            data = data.filter(created_at__gte=start_date)
        if end_date:
            data = data.filter(created_at__lte=end_date)
        context['data'] = data
    elif report_type == 'payments':
        data = access.visible_payments(request.user).filter(status='success').select_related('user', 'booking')
        if start_date:
            data = data.filter(payment_date__gte=start_date)
        if end_date:
            data = data.filter(payment_date__lte=end_date)
        context['data'] = data
    elif report_type == 'rooms':
        context['data'] = access.visible_rooms(request.user).select_related('hostel')
    elif report_type == 'complaints':
        context['data'] = access.visible_complaints(request.user).select_related('user', 'assigned_to')
    elif report_type == 'revenue':
        context['year'] = year
        context['grand_total'] = 0
        payments = Payment.objects.filter(status='success', payment_date__year=year)
        monthly = list(
            payments.extra(select={'month': "strftime('%%m', payment_date)"})
            .values('month')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('month')
        )
        monthly_map = {m['month']: m for m in monthly}
        revenue_data = []
        grand_total = 0
        for i in range(1, 13):
            key = f'{i:02d}'
            m = monthly_map.get(key, {})
            total = float(m.get('total', 0))
            grand_total += total
            revenue_data.append({
                'month_name': f'{calendar.month_name[i]} {year}',
                'total': total,
                'count': m.get('count', 0),
            })
        context['data'] = revenue_data
        context['grand_total'] = grand_total
    else:
        context['data'] = []

    from django.template.loader import render_to_string
    from django.template.exceptions import TemplateDoesNotExist

    try:
        html = render_to_string('hms/reports/pdf_template.html', context)
    except TemplateDoesNotExist:
        html = render_to_string('reports/report_index.html', {'error': 'PDF template not found'})

    try:
        from xhtml2pdf import pisa
        result = io.BytesIO()
        pdf_status = pisa.CreatePDF(io.BytesIO(html.encode('utf-8')), dest=result)
        if not pdf_status.err:
            response = HttpResponse(result.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{report_type}_report.pdf"'
            return response
    except Exception:
        pass

    return HttpResponse(html, content_type='text/html')


@login_required
@manager_required
def export_excel(request, report_type):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        messages.error(request, 'openpyxl is required for Excel export.')
        return redirect('report_index')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f'{report_type.title()} Report'

    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center')

    def style_header(ws, headers):
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

    def auto_width(ws):
        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = min(max_length + 3, 60)

    if report_type == 'bookings':
        headers = ['Reference', 'Renter', 'Room', 'Check In', 'Check Out', 'Status', 'Amount', 'Payment', 'Created']
        style_header(ws, headers)
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        data = access.visible_bookings(request.user).select_related('user', 'bed', 'room__hostel')
        if start_date:
            data = data.filter(created_at__gte=start_date)
        if end_date:
            data = data.filter(created_at__lte=end_date)
        for b in data:
            ws.append([
                b.booking_reference, b.user.full_name,
                f'{b.room.hostel.name} - {b.room.room_number}',
                str(b.check_in), str(b.check_out or ''),
                b.status, float(b.total_amount), b.payment_status,
                b.created_at.strftime('%Y-%m-%d'),
            ])

    elif report_type == 'payments':
        headers = ['Transaction ID', 'User', 'Booking', 'Amount', 'Method', 'Date']
        style_header(ws, headers)
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        data = access.visible_payments(request.user).filter(status='success').select_related('user', 'booking')
        if start_date:
            data = data.filter(payment_date__gte=start_date)
        if end_date:
            data = data.filter(payment_date__lte=end_date)
        for p in data:
            ws.append([
                p.transaction_id, p.user.full_name if p.user else '',
                p.booking.booking_reference if p.booking else '',
                float(p.amount), p.payment_method,
                p.payment_date.strftime('%Y-%m-%d %H:%M'),
            ])

    elif report_type == 'rooms':
        headers = ['Hostel', 'Room No', 'Floor', 'Capacity', 'Rent', 'Status']
        style_header(ws, headers)
        data = access.visible_rooms(request.user).select_related('hostel')
        for r in data:
            ws.append([r.hostel.name, r.room_number, r.floor_number, r.max_occupancy, float(r.rent), r.status])

    elif report_type == 'complaints':
        headers = ['User', 'Category', 'Subject', 'Status', 'Assigned To', 'Created']
        style_header(ws, headers)
        data = access.visible_complaints(request.user).select_related('user', 'assigned_to')
        for c in data:
            ws.append([
                c.user.full_name, c.category, c.subject, c.status,
                c.assigned_to.full_name if c.assigned_to else '',
                c.created_at.strftime('%Y-%m-%d'),
            ])

    elif report_type == 'revenue':
        headers = ['Month', 'Total Revenue (BDT)', 'Transactions']
        style_header(ws, headers)
        year = request.GET.get('year', str(date.today().year))
        monthly = (
            access.visible_payments(request.user).filter(status='success', payment_date__year=year)
            .extra(select={'month': "strftime('%%m', payment_date)"})
            .values('month')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('month')
        )
        for m in monthly:
            month_name = calendar.month_name[int(m['month'])]
            ws.append([f'{month_name} {year}', float(m['total']), m['count']])

    else:
        ws.append(['No data available for this report type.'])

    auto_width(ws)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{report_type}_report.xlsx"'
    return response


# ============================================================
# 12. MEAL MANAGEMENT
# ============================================================

MEAL_TIMES = {
    'breakfast': 7,
    'lunch': 12,
    'dinner': 19,
}


def _lock_expired_preferences():
    """Lock expired meal preferences and sync daily meal bills for locked meals.

    A meal becomes locked (and therefore chargeable) once its cutoff has passed, where
    cutoff = meal time - configured cutoff_hours. Locking and UI-locking both use the
    same cutoff time so a renter can toggle a meal ON/OFF freely until its cutoff, after
    which it is immutable and, if ON, is billed at its configured price.

    generate_daily_meal_bill() charges ONLY locked & ON preferences, so the daily bill
    grows through the day idempotently as each meal's cutoff passes.
    """
    now = timezone.now()
    today = now.date()

    # Lock preferences whose cutoff has passed.
    # Today: lock once the current time passes the meal's cutoff (meal time - cutoff_hours).
    # Past dates: always locked. Future dates: never locked.
    prefs_to_lock = MealPreference.objects.filter(is_locked=False).select_related('booking__room__hostel')

    locked_prefs = []
    # Cache cutoff info per hostel for the single Touch and Solve (TNS) Hostel.
    cutoff_cache = {}
    for pref in prefs_to_lock:
        should_lock = False
        if pref.date < today:
            should_lock = True
        elif pref.date == today:
            hostel_id = pref.booking.room.hostel_id
            if hostel_id not in cutoff_cache:
                cutoff_cache[hostel_id] = MealSettings.objects.filter(
                    hostel_id=hostel_id
                ).values_list('cutoff_hours', flat=True).first() or 0
            cutoff_hours = cutoff_cache[hostel_id]
            meal_hour = MEAL_TIMES.get(pref.meal_type, 0)
            cutoff_hour = meal_hour - cutoff_hours
            if (now.hour > cutoff_hour) or (now.hour == cutoff_hour and now.minute > 0):
                should_lock = True

        if should_lock:
            pref.is_locked = True
            locked_prefs.append(pref)

    if locked_prefs:
        MealPreference.objects.bulk_update(locked_prefs, ['is_locked'])

    _sync_chargeable_bills(today)


def _sync_chargeable_bills(today):
    """Regenerate daily meal bills for every booking that has any locked meal preference
    on or before ``today``. Idempotent via update_or_create on (booking, date).

    Because generate_daily_meal_bill() charges ONLY locked & ON preferences, this keeps
    the accumulated daily bill in sync with the renter's actual selections: an ON meal
    that passed its cutoff always appears in the day's bill, while an OFF meal never
    does, and an all-OFF day removes any prior stale bill. Refreshing the page never
    duplicates a charge.
    """
    # Any booking with a locked preference on/before today (ON or OFF) is a candidate so
    # that stale bills for days that became all-OFF are also corrected/removed.
    candidates = (
        MealPreference.objects.filter(
            is_locked=True, date__lte=today,
        )
        .values_list('booking_id', 'date')
        .distinct()
    )
    seen = set()
    for booking_id, pref_date in candidates:
        key = (booking_id, pref_date)
        if key in seen:
            continue
        seen.add(key)
        try:
            booking = Booking.objects.select_related('room__hostel').get(pk=booking_id)
        except Booking.DoesNotExist:
            continue
        generate_daily_meal_bill(booking, pref_date)

    # Also reconcile every existing unpaid meal bill so that any orphaned/stale bill
    # (one whose (booking, date) no longer has a chargeable locked+ON meal, e.g. because
    # its preferences were deleted or turned OFF) is corrected or removed. This keeps
    # Paid/Pending records intact while dropping fabricated unpaid charges.
    orphan_ids = []
    existing_bills = MealBill.objects.filter(is_paid=False, total_amount__gt=0).select_related('booking__room__hostel')
    for mbill in existing_bills:
        chargeable = MealPreference.objects.filter(
            booking=mbill.booking, date=mbill.date, is_locked=True, status='on',
        ).exists()
        if not chargeable:
            orphan_ids.append(mbill.pk)
    if orphan_ids:
        MealBill.objects.filter(pk__in=orphan_ids).update(
            total_breakfasts=0, total_lunches=0, total_dinners=0,
            breakfast_amount=0, lunch_amount=0, dinner_amount=0, total_amount=0,
        )

    # De-tangle in-flight payments that are NOT legitimate monthly-cycle payments.
    # A monthly meal payment intentionally backs several daily bills of the same month
    # and is tagged with metadata['meal_month']. Old buggy in-flight payments (untagged,
    # each meant to cover one daily bill) that somehow point at multiple bills are
    # un-shared so each remaining unpaid bill stands alone and is counted once.
    for payment in Payment.objects.filter(
        payment_type='meal', status__in=['pending', 'processing'],
    ).exclude(metadata__has_key='meal_month'):
        if MealBill.objects.filter(payment=payment).count() > 1:
            bills = list(MealBill.objects.filter(payment=payment).order_by('-date'))
            for mbill in bills[1:]:
                mbill.payment = None
                mbill.save(update_fields=['payment'])


def check_meal_payment_notifications():
    """Check for unpaid meal bills and send notifications."""
    today = timezone.localdate()
    
    # Find unpaid meal bills for today and past dates
    unpaid_bills = MealBill.objects.filter(
        is_paid=False, 
        total_amount__gt=0,
        date__lte=today
    ).select_related('booking__user', 'booking__room', 'booking__bed')
    
    # Check for overdue bills (past dates)
    for bill in unpaid_bills.filter(date__lt=today):
        # Check if we already sent an overdue notification for this bill
        existing = Notification.objects.filter(
            user=bill.booking.user,
            type='meal_overdue',
            related_bill=bill
        ).exists()
        if not existing:
            Notification.objects.create(
                user=bill.booking.user,
                type='meal_overdue',
                title='Meal Payment Overdue',
                message=f'Your meal payment of ৳{bill.total_amount} for {bill.date.strftime("%B %d")} is overdue. Please complete the payment.',
                related_bill=bill
            )
    
    # Check for today's bills that are due (after dinner cutoff - 7 PM)
    now = timezone.now()
    if now.hour >= 19:  # After dinner time
        for bill in unpaid_bills.filter(date=today):
            existing = Notification.objects.filter(
                user=bill.booking.user,
                type='meal_due',
                related_bill=bill
            ).exists()
            if not existing:
                Notification.objects.create(
                    user=bill.booking.user,
                    type='meal_due',
                    title='Meal Payment Due',
                    message=f'Your meal payment of ৳{bill.total_amount} for today ({bill.date.strftime("%B %d")}) is due. Please complete the payment.',
                    related_bill=bill
                )


def generate_daily_meal_bill(booking, date):
    """Generate or update the daily meal bill for a specific date based on locked preferences.

    The charge is derived ONLY from the renter's actual saved preference for
    (booking, date, meal_type): a meal contributes its configured price only when
    that preference is locked AND ON. OFF meals always contribute ৳0.

    If every meal for the day is OFF (or nothing has locked yet), any previously
    created bill for that day is removed so an OFF-only day never leaves behind a
    stale unpaid charge.
    """
    settings = MealSettings.objects.filter(hostel=booking.room.hostel).first()
    if not settings or not settings.is_enabled:
        return None

    # A meal bill can never exist before the renter checked in. If stale rows exist
    # (e.g. from bad seeding), drop them and treat the day as inactive (no charge).
    if booking.check_in and date < booking.check_in:
        MealBill.objects.filter(booking=booking, date=date).delete()
        return None


    # Look up the exact preference for this renter/date/meal-type; charge only when ON.
    prefs = MealPreference.objects.filter(booking=booking, date=date, is_locked=True)
    locked_pref = {p.meal_type: p for p in prefs}

    rates = {
        'breakfast': settings.rate_breakfast,
        'lunch': settings.rate_lunch,
        'dinner': settings.rate_dinner,
    }
    amounts = {}
    totals = {}
    for meal_type in ['breakfast', 'lunch', 'dinner']:
        pref = locked_pref.get(meal_type)
        is_on = bool(pref and pref.status == 'on')
        amounts[meal_type] = rates[meal_type] if is_on else 0
        totals[meal_type] = 1 if is_on else 0

    total_amount = amounts['breakfast'] + amounts['lunch'] + amounts['dinner']

    # All meals OFF (or none locked yet): no charge; drop any stale bill for the day.
    if total_amount == 0:
        MealBill.objects.filter(booking=booking, date=date).delete()
        return None

    bill, created = MealBill.objects.update_or_create(
        booking=booking, date=date,
        defaults={
            'total_breakfasts': totals['breakfast'],
            'total_lunches': totals['lunch'],
            'total_dinners': totals['dinner'],
            'breakfast_amount': amounts['breakfast'],
            'lunch_amount': amounts['lunch'],
            'dinner_amount': amounts['dinner'],
            'total_amount': total_amount,
        }
    )
    return bill


def _get_active_booking(user):
    return Booking.objects.filter(
        user=user, status__in=['confirmed', 'checked_in'],
        room__hostel__meal_settings__is_enabled=True,
    ).select_related('room', 'room__hostel').order_by('-created_at').first()


def _ensure_preferences(booking, days=7):
    hostel = booking.room.hostel
    settings = MealSettings.objects.filter(hostel=hostel).first()
    if not settings or not settings.is_enabled:
        return
    today = timezone.localdate()
    existing = set(
        MealPreference.objects.filter(booking=booking, date__gte=today, date__lt=today + timedelta(days=days))
        .values_list('date', 'meal_type')
    )
    new_prefs = []
    for day_offset in range(days):
        d = today + timedelta(days=day_offset)
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            if (d, meal_type) not in existing:
                new_prefs.append(MealPreference(
                    booking=booking, date=d, meal_type=meal_type, status=settings.default_status
                ))
    MealPreference.objects.bulk_create(new_prefs, ignore_conflicts=True)


@login_required
@manager_required
def meal_settings_list(request):
    """Show meal settings for the single Touch and Solve (TNS) Hostel."""
    hostel = Hostel.objects.filter(slug='nestora-hostel', is_active=True).first()
    if not hostel:
        messages.error(request, 'Touch and Solve (TNS) Hostel not found.')
        return redirect('dashboard_home')
    
    settings = MealSettings.objects.filter(hostel=hostel).first()
    hostel_data = [{
        'hostel': hostel,
        'settings': settings,
    }]
    return render(request, 'meals/meal_settings_list.html', {'hostel_data': hostel_data})


@login_required
def meal_dashboard(request):
    _lock_expired_preferences()
    check_meal_payment_notifications()
    booking = _get_active_booking(request.user)
    if not booking:
        messages.warning(request, 'You have no active booking with meal service enabled.')
        return render(request, 'meals/meal_dashboard.html', {'booking': None, 'calendar_data': []})

    _ensure_preferences(booking)
    hostel = booking.room.hostel
    settings = MealSettings.objects.get(hostel=hostel)
    today = timezone.localdate()

    # Handle AJAX POST for meal toggle
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        pref_id = request.POST.get('pref_id')
        action = request.POST.get('action')
        if pref_id and action in ('on', 'off'):
            try:
                pref = MealPreference.objects.get(pk=pref_id, booking=booking)
                if pref.is_locked:
                    return JsonResponse({
                        'success': False, 
                        'error': f'{pref.get_meal_type_display()} for {pref.date} is locked. Past deadline.'
                    }, status=400)
                pref.status = action
                pref.save()
                # Re-sync the daily bill so the change is reflected immediately (an ON
                # meal past cutoff becomes chargeable, an OFF meal no longer is).
                generate_daily_meal_bill(booking, pref.date)
                return JsonResponse({
                    'success': True,
                    'status': action,
                    'message': f'{pref.get_meal_type_display()} for {pref.date} set to {action.upper()}.'
                })
            except MealPreference.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Invalid preference.'}, status=404)
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    if request.method == 'POST':
        pref_id = request.POST.get('pref_id')
        action = request.POST.get('action')
        if pref_id and action in ('on', 'off'):
            try:
                pref = MealPreference.objects.get(pk=pref_id, booking=booking)
                if pref.is_locked:
                    messages.error(request, f'{pref.get_meal_type_display()} for {pref.date} is locked. Past deadline.')
                else:
                    pref.status = action
                    pref.save()
                    generate_daily_meal_bill(booking, pref.date)
                    messages.success(request, f'{pref.get_meal_type_display()} for {pref.date} set to {action.upper()}.')
            except MealPreference.DoesNotExist:
                messages.error(request, 'Invalid preference.')
        return redirect('meal_dashboard')

    prefs = MealPreference.objects.filter(booking=booking, date__gte=today, date__lt=today + timedelta(days=7))
    prefs_map = {}
    for p in prefs:
        if p.date not in prefs_map:
            prefs_map[p.date] = {}
        prefs_map[p.date][p.meal_type] = p

    calendar_data = []
    for day_offset in range(7):
        d = today + timedelta(days=day_offset)
        meals = {}
        for mt in ['breakfast', 'lunch', 'dinner']:
            pref = prefs_map.get(d, {}).get(mt)
            cutoff_hour = MEAL_TIMES[mt] - settings.cutoff_hours
            is_past = (d == today and timezone.now().hour >= MEAL_TIMES[mt]) or d < today
            is_locked_by_cutoff = (d == today and timezone.now().hour >= cutoff_hour) or (pref and pref.is_locked)
            meals[mt] = {
                'pref': pref,
                'status': pref.status if pref else settings.default_status,
                'locked': is_locked_by_cutoff or is_past,
            }
        calendar_data.append({'date': d, 'meals': meals, 'is_today': d == today})

    return render(request, 'meals/meal_dashboard.html', {
        'booking': booking,
        'calendar_data': calendar_data,
        'settings': settings,
    })


@login_required
@manager_required
def meal_settings_view(request, hostel_id):
    """Meal settings for the single Touch and Solve (TNS) Hostel. hostel_id is ignored."""
    hostel = Hostel.objects.filter(slug='nestora-hostel', is_active=True).first()
    if not hostel:
        messages.error(request, 'Touch and Solve (TNS) Hostel not found.')
        return redirect('meal_settings_list')
    
    # Verify user has access to this hostel
    if request.user.role == 'HOSTEL_MANAGER':
        if not Hostel.objects.filter(pk=hostel.pk, manager=request.user).exists():
            raise PermissionDenied('This hostel is not assigned to you.')
    
    settings, created = MealSettings.objects.get_or_create(hostel=hostel)
    if request.method == 'POST':
        form = MealSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, f'Meal settings for {hostel.name} updated.')
            return redirect('meal_count')
    else:
        form = MealSettingsForm(instance=settings)
    return render(request, 'meals/meal_settings.html', {'form': form, 'hostel': hostel, 'settings': settings})


@login_required
@manager_required
def meal_service_toggle(request, hostel_id):
    """AJAX endpoint to toggle meal service on/off for Touch and Solve (TNS) Hostel."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    hostel = Hostel.objects.filter(slug='nestora-hostel', is_active=True).first()
    if not hostel:
        return JsonResponse({'success': False, 'error': 'Touch and Solve (TNS) Hostel not found'}, status=404)
    
    # Verify user has access to this hostel
    if request.user.role == 'HOSTEL_MANAGER':
        if not Hostel.objects.filter(pk=hostel.pk, manager=request.user).exists():
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    settings, created = MealSettings.objects.get_or_create(hostel=hostel)
    settings.is_enabled = not settings.is_enabled
    settings.save(update_fields=['is_enabled', 'updated_at'])
    status = 'enabled' if settings.is_enabled else 'disabled'
    messages.success(request, f'Meal service {status} successfully.')
    return JsonResponse({
        'success': True,
        'is_enabled': settings.is_enabled,
        'status': status,
    })


@login_required
@manager_required
def meal_count(request):
    _lock_expired_preferences()
    hostel = Hostel.objects.filter(slug='nestora-hostel', is_active=True).first()
    if not hostel:
        messages.error(request, 'Touch and Solve (TNS) Hostel not found.')
        return redirect('dashboard_home')
    
    date_str = request.GET.get('date')
    try:
        target_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        target_date = timezone.localdate()

    hostel_prefs = MealPreference.objects.filter(
        booking__room__hostel=hostel, date=target_date, is_locked=True
    )
    counts = [{
        'hostel': hostel,
        'breakfast_on': hostel_prefs.filter(meal_type='breakfast', status='on').count(),
        'breakfast_total': hostel_prefs.filter(meal_type='breakfast').count(),
        'lunch_on': hostel_prefs.filter(meal_type='lunch', status='on').count(),
        'lunch_total': hostel_prefs.filter(meal_type='lunch').count(),
        'dinner_on': hostel_prefs.filter(meal_type='dinner', status='on').count(),
        'dinner_total': hostel_prefs.filter(meal_type='dinner').count(),
    }]

    return render(request, 'meals/meal_count.html', {
        'counts': counts,
        'target_date': target_date,
    })


@login_required
@manager_required
def meal_payment_monitor(request):
    """Manager/Admin meal payment monitoring page."""
    _lock_expired_preferences()
    check_meal_payment_notifications()
    date_filter = request.GET.get('date')
    status_filter = request.GET.get('status')
    q = request.GET.get('q', '')
    
    bills = access.visible_meal_bills(request.user).select_related(
        'booking__user', 'booking__room', 'booking__bed', 'payment'
    )
    
    if date_filter:
        try:
            bills = bills.filter(date=date.fromisoformat(date_filter))
        except ValueError:
            pass
    else:
        # Default to today
        bills = bills.filter(date=timezone.localdate())
    
    if status_filter == 'paid':
        bills = bills.filter(is_paid=True)
    elif status_filter == 'unpaid':
        bills = bills.filter(is_paid=False)
    elif status_filter == 'overdue':
        # Overdue: unpaid bills for past dates
        bills = bills.filter(is_paid=False, date__lt=timezone.localdate())
    
    if q:
        bills = bills.filter(
            Q(booking__user__full_name__icontains=q) |
            Q(booking__user__email__icontains=q) |
            Q(booking__room__room_number__icontains=q) |
            Q(booking__bed__bed_number__icontains=q)
        )
    
    bills = bills.order_by('-date', 'booking__room__room_number', 'booking__bed__bed_number')
    paginator = Paginator(bills, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary stats
    today = timezone.localdate()
    total_bills = bills.count()
    paid_bills = bills.filter(is_paid=True).count()
    unpaid_bills = bills.filter(is_paid=False).count()
    overdue_bills = bills.filter(is_paid=False, date__lt=today).count()
    total_amount = bills.aggregate(total=Sum('total_amount'))['total'] or 0
    paid_amount = bills.filter(is_paid=True).aggregate(total=Sum('total_amount'))['total'] or 0
    due_amount = total_amount - paid_amount
    
    return render(request, 'meals/meal_payment_monitor.html', {
        'page_obj': page_obj,
        'bills': page_obj.object_list,
        'date_filter': date_filter or today,
        'status_filter': status_filter,
        'query': q,
        'total_bills': total_bills,
        'paid_bills': paid_bills,
        'unpaid_bills': unpaid_bills,
        'overdue_bills': overdue_bills,
        'total_amount': total_amount,
        'paid_amount': paid_amount,
        'due_amount': due_amount,
    })


@login_required
@manager_required
def meal_bill_mark_paid(request, pk):
    """Manager/Admin marks a meal bill as paid (COD/manual)."""
    if request.method != 'POST':
        return redirect('meal_bill_detail', pk=pk)

    bill = get_object_or_404(access.visible_meal_bills(request.user), pk=pk)
    if bill.is_paid:
        messages.info(request, 'This meal bill is already marked as paid.')
        return redirect('meal_payment_monitor')

    # A future-dated meal bill is not yet payable and must not be marked as paid.
    if bill.date > timezone.localdate():
        messages.error(request, 'This meal bill is not payable yet (future date).')
        return redirect('meal_payment_monitor')

    payment_method = request.POST.get('payment_method', 'cod').lower()
    with transaction.atomic():
        payment = Payment.objects.create(
            booking=bill.booking,
            user=bill.booking.user,
            transaction_id=generate_transaction_id(),
            amount=bill.total_amount,
            currency='BDT',
            status='success',
            payment_type='meal',
            payment_method='cod',
        )
        bill.payment = payment
        bill.is_paid = True
        bill.save(update_fields=['payment', 'is_paid', 'updated_at'])
        Notification.objects.create(
            user=bill.booking.user,
            type='meal_paid',
            title='Meal Payment Received',
            message=f'Your meal payment of ৳{bill.total_amount} for {bill.date.strftime("%B %d")} has been received.',
            related_bill=bill
        )
    messages.success(request, f'Meal bill for {bill.booking.user.full_name} on {bill.date} marked as paid.')
    return redirect('meal_payment_monitor')


@login_required
def meal_bill_detail(request, pk):
    bill = get_object_or_404(access.visible_meal_bills(request.user), pk=pk)
    return render(request, 'meals/meal_bill_detail.html', {'bill': bill})


def _meal_bill_status(bill):
    """Return (status_label, badge_class) for a single meal bill.

    Precedence: Paid > Payment Pending (in-flight gateway payment) > Failed >
    Unpaid. A None bill (e.g. today with no charge yet) is reported as unpaid/neutral.
    """
    if not bill:
        return ('Unpaid', 'badge-pending')
    if bill.is_paid:
        return ('Paid', 'badge-success')
    payment = bill.payment
    if payment and payment.status in ('pending', 'processing'):
        return ('Payment Pending', 'badge-warning')
    if payment and payment.status == 'failed':
        return ('Failed', 'badge-danger')
    return ('Unpaid', 'badge-pending')


def _meal_month_total(booking, year, month, settings):
    """Monthly meal charge for (year, month) = sum of every locked+ON meal across all days
    of the month. OFF (or unset) meals contribute ০0, so turning a meal off deducts it.
    Only locked preferences count, matching how a daily bill is derived."""
    if not settings:
        return 0
    rates = {'breakfast': settings.rate_breakfast,
             'lunch': settings.rate_lunch,
             'dinner': settings.rate_dinner}
    # Only days during the stay (>= check-in, < check-out) may be charged. Any meals
    # recorded before check-in or after check-out are invalid and excluded.
    def _active(d):
        if booking.check_in and d < booking.check_in:
            return False
        if booking.check_out and d >= booking.check_out:
            return False
        return True

    prefs = MealPreference.objects.filter(
        booking=booking, date__year=year, date__month=month, is_locked=True)
    daymap = {}
    for p in prefs:
        if _active(p.date):
            daymap.setdefault(p.date, {})[p.meal_type] = (p.status or 'off').strip().lower()
    total = 0
    for row in daymap.values():
        for mt, rate in rates.items():
            if row.get(mt) == 'on':
                total += rate
    return total


def _meal_month_payable(year, month, today):
    """A month's bill becomes payable the day AFTER the month ends (next-day rule): the
    last day of month M is charged, and its pay option appears the following day."""
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return today > last_day


def _meal_month_settled(booking, year, month):
    return Payment.objects.filter(
        user=booking.user, payment_type='meal', status='success',
        metadata__meal_month='{:04d}-{:02d}'.format(year, month),
    ).exists()


def _meal_month_pending(booking, year, month):
    return Payment.objects.filter(
        user=booking.user, payment_type='meal',
        status__in=['pending', 'processing'],
        metadata__meal_month='{:04d}-{:02d}'.format(year, month),
    ).exists()


def _meal_covered_months(booking, today):
    """(year, month) keys of every month between the renter's meal-service start and today,
    newest first. Always includes the current month so the "not yet payable" row shows."""
    months = set()
    for d in MealPreference.objects.filter(booking=booking).order_by('date').values_list('date', flat=True):
        if d <= today:
            months.add((d.year, d.month))
    if booking.check_in and booking.check_in <= today:
        months.add((booking.check_in.year, booking.check_in.month))
    months.add((today.year, today.month))
    return sorted(months, reverse=True)


@login_required
def my_meal_bills(request):
    """Renter's daily meal bills page."""
    _lock_expired_preferences()
    check_meal_payment_notifications()
    booking = _get_active_booking(request.user)
    
    if not booking:
        today = timezone.localdate()
        return render(request, 'meals/my_meal_bills.html', {
            'booking': None,
            'today_bill': None,
            'recent_bills': [],
            'total_unpaid': 0,
            'today': today,
        })
    
    today = timezone.localdate()
    settings = MealSettings.objects.filter(hostel=booking.room.hostel).first()

    # Sync today's bill from the renter's locked/chargeable preferences.
    # This recomputes the accumulated total (breakfast -> lunch -> dinner) and is
    # idempotent, so refreshing the page never duplicates a charge.
    today_bill = generate_daily_meal_bill(booking, today)

    # Get recent bills (last 7 days, including today)
    recent_bills = list(
        MealBill.objects.filter(
            booking=booking, date__lte=today
        ).select_related('payment').order_by('-date')[:7]
    )
    _bill_statuses = {
        'Unpaid': 'badge-pending',
        'Payment Pending': 'badge-warning',
        'Paid': 'badge-success',
        'Failed': 'badge-danger',
    }
    for b in recent_bills:
        b.payment_status, b.payment_badge = _meal_bill_status(b)

    # ---- Daily billing (one payment per day) ------------------------------------
    # Each day's MealBill is payable on its own. A bill becomes payable as soon as the
    # day is over its meal cutoff (i.e. on/after its own date). Outstanding balance is
    # the sum of every unpaid, payable (past or today) daily bill. No month-level
    # aggregation is used on this page.
    outstanding_bills = list(
        MealBill.objects.filter(
            booking=booking, date__lte=today, is_paid=False, total_amount__gt=0
        ).select_related('payment').order_by('-date')
    )
    for b in outstanding_bills:
        b.payment_status, b.payment_badge = _meal_bill_status(b)
    total_unpaid = sum(b.total_amount for b in outstanding_bills)

    rates = {
        'breakfast': settings.rate_breakfast if settings else 0,
        'lunch': settings.rate_lunch if settings else 0,
        'dinner': settings.rate_dinner if settings else 0,
    }

    # Today's meal status: chargeable only when locked AND ON (i.e. past its cutoff).
    # A MISSING preference is treated as OFF (never ON), so a meal with no saved
    # preference is never accidentally charged. OFF meals are always ৳0.
    today_prefs = MealPreference.objects.filter(booking=booking, date=today)
    today_meals = {}
    chargeable_total = 0
    for mt in ['breakfast', 'lunch', 'dinner']:
        pref = today_prefs.filter(meal_type=mt).first()
        status = pref.status if pref else 'off'
        locked = bool(pref and pref.is_locked)
        chargeable = locked and status == 'on'
        amount = rates[mt] if chargeable else 0
        if chargeable:
            chargeable_total += amount
        today_meals[mt] = {
            'status': status,
            'locked': locked,
            'chargeable': chargeable,
            'amount': amount,
        }

    # The displayed total is single-sourced from the renter's actual locked+ON
    # preferences (chargeable_total). generate_daily_meal_bill() removed/verified the
    # stored daily bill and it is guaranteed to equal chargeable_total whenever a
    # charge exists, so we never surface a stale amount for an OFF meal.
    today_is_paid = bool(today_bill and today_bill.is_paid)
    today_bill_total = chargeable_total
    today_status, today_badge = _meal_bill_status(today_bill)

    return render(request, 'meals/my_meal_bills.html', {
        'booking': booking,
        'today_bill': today_bill,
        'today_meals': today_meals,
        'chargeable_total': today_bill_total,
        'today_is_paid': today_is_paid,
        'today_status': today_status,
        'today_badge': today_badge,
        'recent_bills': recent_bills,
        'outstanding_bills': outstanding_bills,
        'total_unpaid': total_unpaid,
        'settings': settings,
        'today': today,
    })


@login_required
def meal_pay(request, pk):
    """Renter initiates payment for a meal bill."""
    bill = get_object_or_404(access.visible_meal_bills(request.user), pk=pk, is_paid=False)
    payer = bill.booking.user

    # Backend enforcement: a future-dated meal bill is NOT payable yet, even if
    # someone manually crafts the URL or POST request. Only today's and past
    # (payable) bills can be paid. No Payment object is created and nothing is
    # charged for a future-dated bill.
    today = timezone.localdate()
    if bill.date > today:
        messages.error(
            request,
            'This meal bill is not payable yet. Payment will be available on the bill '
            'date after the applicable meal cutoff.',
        )
        return redirect('my_meal_bills')

    # Reuse ONLY the in-flight payment already attached to THIS bill so a double-click /
    # refresh / resubmit never creates duplicate payments. Never reuse a payment that
    # belongs to a different bill (that produced one in-flight payment shared across many
    # bills). Each bill must be settled by its own single transaction.
    payment = bill.payment
    if not (payment and payment.status in ('pending', 'processing')):
        payment = Payment.objects.create(
            booking=bill.booking,
            user=payer,
            transaction_id=generate_transaction_id(),
            amount=bill.total_amount,
            currency='BDT',
            status='pending',
            payment_type='meal',
        )
    bill.payment = payment
    bill.save()

    payload = {
        'store_id': settings.SSL_COMMERZ_STORE_ID,
        'store_passwd': settings.SSL_COMMERZ_STORE_PASSWORD,
        'total_amount': str(payment.amount),
        'currency': payment.currency,
        'tran_id': payment.transaction_id,
        'success_url': request.build_absolute_uri(reverse('payment_success')),
        'fail_url': request.build_absolute_uri(reverse('payment_fail')),
        'cancel_url': request.build_absolute_uri(reverse('payment_fail')),
        'ipn_url': request.build_absolute_uri(reverse('ssl_ipn')),
        'emi_allow': 0,
        'cus_name': payer.full_name,
        'cus_email': payer.email,
        'cus_add1': bill.booking.room.hostel.address,
        'cus_phone': payer.phone or '',
        'shipping_method': 'NO',
        'product_name': f'Meal Bill - {bill.date}',
        'product_category': 'Meal',
        'product_profile': 'general',
    }
    try:
        resp = requests.post(settings.SSLCOMMERZ_API_URL, data=payload, timeout=30)
        resp_data = resp.json()
        if resp_data.get('status') == 'SUCCESS':
            payment.status = 'processing'
            payment.metadata = {'GatewayPageURL': resp_data.get('GatewayPageURL'), 'meal_bill': bill.pk}
            payment.save()
            return redirect(resp_data['GatewayPageURL'])
        else:
            payment.delete()
            bill.payment = None
            bill.save()
            messages.error(request, 'Payment gateway error. Please try again.')
    except Exception as e:
        payment.delete()
        bill.payment = None
        bill.save()
        messages.error(request, f'Payment initiation failed: {str(e)}')

    return redirect('meal_bill_detail', pk=pk)


@login_required
def meal_pay_month(request, year, month):
    """Renter pays a whole calendar month of meal charges (locked+ON meals across all
    days of the month, OFF meals deducted) in ONE payment. Enforced payable only after
    the month ends (next-day rule)."""
    year, month = int(year), int(month)
    booking = _get_active_booking(request.user)
    if not booking:
        messages.error(request, 'No active booking found.')
        return redirect('my_meal_bills')
    meal_settings = MealSettings.objects.filter(hostel=booking.room.hostel).first()
    today = timezone.localdate()
    month_key = '{:04d}-{:02d}'.format(year, month)

    # Payable only the day AFTER the month ends.
    if not _meal_month_payable(year, month, today):
        messages.error(
            request,
            'This month is not payable yet. Payment becomes available the day after '
            'the month ends.',
        )
        return redirect('my_meal_bills')

    if _meal_month_settled(booking, year, month):
        messages.info(request, 'This month has already been paid.')
        return redirect('my_meal_bills')

    month_total = _meal_month_total(booking, year, month, meal_settings)
    if month_total <= 0:
        messages.info(request, 'Nothing to pay for this month.')
        return redirect('my_meal_bills')

    # Reuse an in-flight payment already opened for this exact month (idempotency on
    # double-click / refresh); otherwise open a fresh monthly payment. Each monthly
    # payment is tagged with metadata['meal_month'] so it is recognized as a legit,
    # half-open monthly transaction (not de-tangled) and is the single settlement for
    # the month.
    payment = Payment.objects.filter(
        user=booking.user, payment_type='meal',
        status__in=['pending', 'processing'],
        metadata__meal_month=month_key,
    ).first()
    if not payment:
        payment = Payment.objects.create(
            booking=booking,
            user=booking.user,
            transaction_id=generate_transaction_id(),
            amount=month_total,
            currency='BDT',
            status='pending',
            payment_type='meal',
            metadata={'meal_month': month_key},
        )
    # Attach the monthly payment to the month's unpaid daily bills (line-item sync only;
    # the single payment amount is the authoritative monthly total).
    MealBill.objects.filter(
        booking=booking, is_paid=False, date__year=year, date__month=month,
    ).update(payment=payment)

    payload = {
        'store_id': settings.SSL_COMMERZ_STORE_ID,
        'store_passwd': settings.SSL_COMMERZ_STORE_PASSWORD,
        'total_amount': str(month_total),
        'currency': payment.currency,
        'tran_id': payment.transaction_id,
        'success_url': request.build_absolute_uri(reverse('payment_success')),
        'fail_url': request.build_absolute_uri(reverse('payment_fail')),
        'cancel_url': request.build_absolute_uri(reverse('payment_fail')),
        'ipn_url': request.build_absolute_uri(reverse('ssl_ipn')),
        'emi_allow': 0,
        'cus_name': booking.user.full_name,
        'cus_email': booking.user.email,
        'cus_add1': booking.room.hostel.address,
        'cus_phone': booking.user.phone or '',
        'shipping_method': 'NO',
        'product_name': 'Meal Bill - {} {}'.format(month, year),
        'product_category': 'Meal',
        'product_profile': 'general',
    }
    try:
        resp = requests.post(settings.SSLCOMMERZ_API_URL, data=payload, timeout=30)
        resp_data = resp.json()
        if resp_data.get('status') == 'SUCCESS':
            payment.status = 'processing'
            payment.metadata.update({'GatewayPageURL': resp_data.get('GatewayPageURL')})
            payment.save()
            return redirect(resp_data['GatewayPageURL'])
        else:
            # gateway rejected: drop the monthly payment and leave the month payable
            MealBill.objects.filter(
                booking=booking, date__year=year, date__month=month,
            ).update(payment=None)
            payment.delete()
            messages.error(request, 'Payment gateway error. Please try again.')
    except Exception as e:
        MealBill.objects.filter(
            booking=booking, date__year=year, date__month=month,
        ).update(payment=None)
        payment.delete()
        messages.error(request, f'Payment initiation failed: {str(e)}')

    return redirect('my_meal_bills')


@login_required
@manager_required
def process_refund(request, pk):
    refund = get_object_or_404(
        Refund.objects.select_related('cancellation__booking__room__hostel', 'payment'),
        pk=pk,
    )
    booking = refund.cancellation.booking
    if request.user.role == 'HOSTEL_MANAGER' and booking.room.hostel != access.get_manager_hostel(request.user):
        messages.error(request, 'Access denied.')
        return redirect('refund_list')
    if refund.status != 'pending':
        messages.error(request, 'This refund has already been processed.')
        return redirect('booking_detail', pk=booking.pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            refund.status = 'completed'
            refund.processed_by = request.user
            refund.notes = request.POST.get('notes', '')
            refund.save()
            messages.success(request, f'Refund of ৳{refund.amount} completed.')
        elif action == 'reject':
            refund.status = 'failed'
            refund.processed_by = request.user
            refund.notes = request.POST.get('notes', '')
            refund.save()
            messages.warning(request, f'Refund of ৳{refund.amount} rejected.')
        return redirect('booking_detail', pk=booking.pk)
    return render(request, 'bookings/process_refund.html', {'refund': refund})


@login_required
def refund_list(request):
    refunds = access.visible_refunds(request.user)
    status_filter = request.GET.get('status')
    if status_filter:
        refunds = refunds.filter(status=status_filter)
    paginator = Paginator(refunds.order_by('-created_at'), 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'bookings/refund_list.html', {'page_obj': page_obj, 'selected_status': status_filter})


