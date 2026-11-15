from django.contrib import admin
from .models import (
    User, Hostel, RoomType, Floor, Unit, Room, Bed,
    Booking, Payment, Cancellation, Refund,
    Complaint, Notice, Visitor,
    MealSettings, MealPreference, MealBill,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "full_name", "phone", "role", "is_active", "date_joined"]
    list_filter = ["role", "is_active", "date_joined"]
    search_fields = ["email", "full_name", "phone"]
    ordering = ["-date_joined"]


@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "manager", "contact_phone", "is_active", "created_at"]
    list_filter = ["city", "is_active", "created_at"]
    search_fields = ["name", "city", "manager__full_name", "manager__email"]
    ordering = ["name"]


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "default_capacity", "default_rent", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 0


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ["__str__", "hostel", "number", "name"]
    list_filter = ["hostel"]
    search_fields = ["hostel__name", "name"]
    inlines = [UnitInline]


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ["__str__", "floor", "name"]
    list_filter = ["floor__hostel"]
    search_fields = ["name", "floor__hostel__name"]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["room_number", "hostel", "unit", "room_type", "rent", "capacity", "status", "floor_number"]
    list_filter = ["hostel", "status", "unit__floor", "room_type"]
    search_fields = ["room_number", "hostel__name"]
    ordering = ["hostel", "room_number"]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ["bed_number", "room", "status", "is_active"]
    list_filter = ["status", "room__hostel"]
    search_fields = ["bed_number", "room__room_number"]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["booking_reference", "user", "room", "bed", "check_in", "check_out", "status", "created_at"]
    list_filter = ["status", "check_in", "check_out"]
    search_fields = ["user__email", "room__room_number", "booking_reference"]
    ordering = ["-created_at"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["transaction_id", "booking", "amount", "payment_date", "status"]
    list_filter = ["status", "payment_date"]
    search_fields = ["booking__user__email", "transaction_id"]
    ordering = ["-payment_date"]


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ["subject", "user", "hostel", "category", "status", "created_at"]
    list_filter = ["status", "category", "created_at"]
    search_fields = ["subject", "user__email"]
    ordering = ["-created_at"]


@admin.register(Cancellation)
class CancellationAdmin(admin.ModelAdmin):
    list_display = ["booking", "cancelled_by", "days_before_checkin", "cancellation_fee", "refund_amount", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["booking__booking_reference"]
    ordering = ["-created_at"]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["cancellation", "amount", "status", "processed_by", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["cancellation__booking__booking_reference"]
    ordering = ["-created_at"]


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ["title", "hostel", "category", "created_by", "is_active", "created_at"]
    list_filter = ["category", "is_active", "created_at"]
    search_fields = ["title", "content"]


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "purpose", "entry_time", "exit_time", "is_inside"]
    list_filter = ["entry_time", "is_inside"]
    search_fields = ["name", "phone", "email"]
    ordering = ["-entry_time"]


@admin.register(MealSettings)
class MealSettingsAdmin(admin.ModelAdmin):
    list_display = ["hostel", "is_enabled", "default_status", "cutoff_hours", "rate_breakfast", "rate_lunch", "rate_dinner"]
    list_filter = ["is_enabled"]


@admin.register(MealPreference)
class MealPreferenceAdmin(admin.ModelAdmin):
    list_display = ["booking", "date", "meal_type", "status", "is_locked"]
    list_filter = ["meal_type", "status", "is_locked", "date"]


@admin.register(MealBill)
class MealBillAdmin(admin.ModelAdmin):
    list_display = ["booking", "month", "total_amount", "is_paid"]
    list_filter = ["is_paid", "month"]
