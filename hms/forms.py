from django import forms
from django.contrib.auth import authenticate
from .models import (
    User, Hostel, RoomType, Floor, Unit, Room, Bed,
    Booking, Complaint, Notice, Visitor,
    MealSettings, MealPreference, MealBill,
)
import re

class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')
        if email and password:
            user = authenticate(email=email, password=password)
            if not user:
                raise forms.ValidationError('Invalid email or password.')
        return cleaned_data


class RenterRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}))

    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone'}),
        }

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters.')
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', password):
            raise forms.ValidationError('Password must contain at least one lowercase letter.')
        if not re.search(r'\d', password):
            raise forms.ValidationError('Password must contain at least one digit.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise forms.ValidationError('Password must contain at least one special character.')
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data



class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['full_name', 'phone', 'photo', 'address', 'emergency_contact']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'emergency_contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Emergency contact phone'}),
        }


class HostelForm(forms.ModelForm):
    class Meta:
        model = Hostel
        fields = [
            'name', 'address', 'city', 'google_map_link', 'description', 'rules',
            'image', 'contact_phone', 'contact_email', 'facilities',
            'confirmation_policy',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'google_map_link': forms.URLInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'rules': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'facilities': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Wi-Fi\nLaundry\nCCTV\nGenerator'}),
            'confirmation_policy': forms.Select(attrs={'class': 'form-control'}),
        }


class HostelManagerAssignForm(forms.ModelForm):
    """Super Admin form for assigning a manager to a hostel."""
    class Meta:
        model = Hostel
        fields = ['manager']
        widgets = {
            'manager': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assigned = Hostel.objects.exclude(manager__isnull=True).exclude(manager=self.instance.manager)
        exclude_ids = list(assigned.values_list('manager_id', flat=True))
        self.fields['manager'].queryset = User.objects.filter(
            role='HOSTEL_MANAGER', is_active=True,
        ).exclude(id__in=exclude_ids)
        self.fields['manager'].required = False
        self.fields['manager'].empty_label = '-- No manager assigned --'


class FloorForm(forms.ModelForm):
    class Meta:
        model = Floor
        fields = ['number', 'name', 'description']
        widgets = {
            'number': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional, e.g. Ground Floor'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_number(self):
        number = self.cleaned_data.get('number')
        if number is None or number < 0:
            raise forms.ValidationError('Floor number must be 0 or greater.')
        return number


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. A'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_name(self):
        return (self.cleaned_data.get('name') or '').strip().upper()


class RoomTypeForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ['name', 'description', 'default_capacity', 'default_rent', 'facilities', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'default_capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'default_rent': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'facilities': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'AC\nWi-Fi\nPersonal Locker\nStudy Table'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BedForm(forms.ModelForm):
    class Meta:
        model = Bed
        fields = ['bed_number', 'status', 'is_active']
        widgets = {
            'bed_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Bed 1'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_bed_number(self):
        bed_number = (self.cleaned_data.get('bed_number') or '').strip()
        if not bed_number:
            raise forms.ValidationError('Bed label is required.')
        return bed_number


class RoomForm(forms.ModelForm):
    num_beds = forms.IntegerField(
        min_value=0, max_value=20, required=False, initial=4,
        label='Number of beds to create',
        help_text='Only used when creating a room. Beds are labelled Bed 1..N.',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 20}),
    )

    class Meta:
        model = Room
        fields = [
            'hostel', 'unit', 'room_type', 'room_number', 'capacity',
            'max_occupancy', 'size_sqft', 'rent', 'security_deposit',
            'is_ac', 'attached_bathroom', 'num_bathrooms', 'has_balcony',
            'amenities', 'description', 'status', 'image', 'is_active',
        ]
        widgets = {
            'hostel': forms.Select(attrs={'class': 'form-control'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
            'room_type': forms.Select(attrs={'class': 'form-control'}),
            'room_number': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'max_occupancy': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'size_sqft': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'rent': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'security_deposit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'is_ac': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'attached_bathroom': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'num_bathrooms': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'has_balcony': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'amenities': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'One amenity per line: Wi-Fi\nStudy Table\nPersonal Locker'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .access import visible_hostels
        if user and user.role == 'HOSTEL_MANAGER':
            self.fields['hostel'].queryset = visible_hostels(user)
            self.fields['hostel'].initial = visible_hostels(user).first()
        else:
            self.fields['hostel'].queryset = Hostel.objects.filter(is_active=True)
        self.fields['unit'].queryset = Unit.objects.select_related('floor', 'floor__hostel').all()
        self.fields['room_type'].queryset = RoomType.objects.filter(is_active=True)
        if self.instance.pk:
            # Editing: restrict units to the room's hostel and hide bed creation.
            self.fields['unit'].queryset = Unit.objects.filter(floor__hostel=self.instance.hostel)
            del self.fields['num_beds']
        if 'unit' in self.data:
            try:
                unit_id = int(self.data.get('unit'))
                self.fields['unit'].queryset = Unit.objects.filter(floor__hostel_id=int(self.data.get('hostel', 0) or 0)) | Unit.objects.filter(pk=unit_id)
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned = super().clean()
        hostel = cleaned.get('hostel')
        unit = cleaned.get('unit')
        if hostel and unit and unit.floor.hostel_id != hostel.id:
            self.add_error('unit', 'Selected unit does not belong to the selected hostel.')
        rent = cleaned.get('rent')
        if rent is not None and rent < 0:
            self.add_error('rent', 'Rent cannot be negative.')
        return cleaned


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['check_in', 'check_out']
        widgets = {
            'check_in': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'check_out': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get('check_in')
        check_out = cleaned.get('check_out')
        from django.utils import timezone
        if check_in and check_in < timezone.now().date():
            raise forms.ValidationError('Check-in date cannot be in the past.')
        if check_in and check_out and check_out <= check_in:
            raise forms.ValidationError('Check-out date must be after the check-in date.')
        return cleaned


class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ['category', 'subject', 'description', 'room', 'priority']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'room': forms.Select(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room'].required = False
        if user:
            # Renters can only complain about rooms they occupy / booked.
            self.fields['room'].queryset = Room.objects.filter(
                bookings__user=user,
                bookings__status__in=['confirmed', 'checked_in'],
            ).distinct()


class ManagerCreateForm(forms.Form):
    """Super Admin creates a Hostel Manager account (no Employee/Payroll records)."""
    full_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
    )
    phone = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone'}),
    )
    initial_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Initial Password'}),
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def clean_initial_password(self):
        password = self.cleaned_data.get('initial_password')
        if len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters.')
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', password):
            raise forms.ValidationError('Password must contain at least one lowercase letter.')
        if not re.search(r'\d', password):
            raise forms.ValidationError('Password must contain at least one digit.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise forms.ValidationError('Password must contain at least one special character.')
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('initial_password')
        confirm = cleaned_data.get('confirm_password')
        if password and confirm and password != confirm:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            email=self.cleaned_data['email'],
            full_name=self.cleaned_data['full_name'],
            password=self.cleaned_data['initial_password'],
            phone=self.cleaned_data.get('phone', ''),
            role='HOSTEL_MANAGER',
            must_change_password=True,
        )
        return user


class ManagerEditForm(forms.Form):
    full_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    phone = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to keep current'}),
        help_text='Leave blank to keep the current password.',
    )
    confirm_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm new password'}),
    )

    def __init__(self, *args, **kwargs):
        self.manager = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        if self.manager:
            self.fields['full_name'].initial = self.manager.full_name
            self.fields['phone'].initial = self.manager.phone
            self.fields['is_active'].initial = self.manager.is_active

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm = cleaned_data.get('confirm_password')
        if new_password:
            if len(new_password) < 8:
                raise forms.ValidationError('Password must be at least 8 characters.')
            if not re.search(r'[A-Z]', new_password):
                raise forms.ValidationError('Password must contain at least one uppercase letter.')
            if not re.search(r'[a-z]', new_password):
                raise forms.ValidationError('Password must contain at least one lowercase letter.')
            if not re.search(r'\d', new_password):
                raise forms.ValidationError('Password must contain at least one digit.')
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password):
                raise forms.ValidationError('Password must contain at least one special character.')
            if new_password != confirm:
                raise forms.ValidationError('Passwords do not match.')
        return cleaned_data

    def save(self):
        self.manager.full_name = self.cleaned_data['full_name']
        self.manager.phone = self.cleaned_data['phone']
        self.manager.is_active = self.cleaned_data['is_active']
        new_password = self.cleaned_data.get('new_password')
        if new_password:
            self.manager.set_password(new_password)
            self.manager.must_change_password = True
        self.manager.save()
        return self.manager


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ['title', 'content', 'category', 'hostel']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'hostel': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .access import visible_hostels
        self.fields['hostel'].required = False
        self.fields['hostel'].empty_label = 'Platform-wide (all hostels)'
        if user and user.role == 'HOSTEL_MANAGER':
            # Managers can only publish notices for their own hostel.
            self.fields['hostel'].queryset = visible_hostels(user)
            self.fields['hostel'].initial = visible_hostels(user).first()
            self.fields['hostel'].empty_label = None


class VisitorForm(forms.ModelForm):
    class Meta:
        model = Visitor
        fields = ['name', 'phone', 'email', 'address', 'purpose', 'host', 'room']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'purpose': forms.TextInput(attrs={'class': 'form-control'}),
            'host': forms.Select(attrs={'class': 'form-control'}),
            'room': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['host'].queryset = User.objects.filter(role='RENTER', is_active=True).order_by('full_name')
        self.fields['host'].required = False
        self.fields['room'].queryset = Room.objects.filter(is_active=True).select_related('unit__floor').order_by('room_number')
        self.fields['room'].required = False


class AllocationOverrideForm(forms.Form):
    def __init__(self, *args, booking=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .access import visible_rooms
        queryset = visible_rooms(user).filter(is_active=True, status='available')
        if booking and user.role == 'HOSTEL_MANAGER':
            # Managers may only reassign within their own hostel.
            queryset = queryset.filter(hostel=booking.room.hostel)
        self.fields['new_room'].queryset = queryset

    new_room = forms.ModelChoiceField(
        queryset=Room.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Reassign to Room',
    )
    justification = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter reason for override...'}),
        label='Justification (required for audit)',
    )


# ============================================================
# MEAL FORMS
# ============================================================

class MealSettingsForm(forms.ModelForm):
    class Meta:
        model = MealSettings
        fields = ['is_enabled', 'default_status', 'cutoff_hours', 'rate_breakfast', 'rate_lunch', 'rate_dinner']
        widgets = {
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_status': forms.Select(attrs={'class': 'form-control'}),
            'cutoff_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 24}),
            'rate_breakfast': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'rate_lunch': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'rate_dinner': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
