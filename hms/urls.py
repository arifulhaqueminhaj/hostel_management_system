from django.urls import path
from . import views

urlpatterns = [
    # Role-specific Auth
    path('login/super-admin/', views.super_admin_login, name='super_admin_login'),
    path('login/manager/', views.employee_login, name='employee_login'),
    path('login/renter/', views.renter_login, name='renter_login'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password_view, name='change_password'),
    path('register/', views.register_view, name='register'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile_view, name='edit_profile'),

    # Public
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),

    # Hostels
    path('hostels/', views.hostel_list, name='hostel_list'),
    path('hostels/<slug:slug>/', views.hostel_detail, name='hostel_detail'),
    path('hostels/<slug:slug>/edit/', views.hostel_edit, name='hostel_edit'),
    path('hostels/<slug:slug>/delete/', views.hostel_delete, name='hostel_delete'),
    path('hostels/<slug:slug>/assign-manager/', views.assign_manager, name='assign_manager'),

    # Structure: Floors / Units / Room Types / Rooms / Beds
    path('hostels/<int:hostel_id>/floors/', views.floor_list, name='floor_list'),
    path('hostels/<int:hostel_id>/floors/add/', views.floor_add, name='floor_add'),
    path('floors/<int:pk>/edit/', views.floor_edit, name='floor_edit'),
    path('floors/<int:pk>/delete/', views.floor_delete, name='floor_delete'),
    path('floors/<int:floor_id>/units/', views.unit_list, name='unit_list'),
    path('floors/<int:floor_id>/units/add/', views.unit_add, name='unit_add'),
    path('units/<int:pk>/edit/', views.unit_edit, name='unit_edit'),
    path('units/<int:pk>/delete/', views.unit_delete, name='unit_delete'),
    path('room-types/', views.room_type_list, name='room_type_list'),
    path('room-types/add/', views.room_type_add, name='room_type_add'),
    path('room-types/<int:pk>/edit/', views.room_type_edit, name='room_type_edit'),
    path('room-types/<int:pk>/delete/', views.room_type_delete, name='room_type_delete'),
    path('rooms/', views.room_list, name='room_list'),
    path('rooms/add/', views.room_add, name='room_add'),
    path('rooms/<int:pk>/', views.room_detail, name='room_detail'),
    path('rooms/<int:pk>/edit/', views.room_edit, name='room_edit'),
    path('rooms/<int:pk>/delete/', views.room_delete, name='room_delete'),
    path('rooms/<int:room_id>/beds/', views.bed_manage, name='bed_manage'),

    # Search & Availability
    path('search-rooms/', views.search_rooms, name='search_rooms'),
    path('check-availability/', views.check_availability, name='check_availability'),

    # Bookings
    path('bookings/create/<int:room_id>/', views.create_booking, name='create_booking'),
    path('bookings/my/', views.my_bookings, name='my_bookings'),
    path('bookings/all/', views.all_bookings, name='all_bookings'),
    path('bookings/<int:pk>/', views.booking_detail, name='booking_detail'),
    path('bookings/<int:pk>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('bookings/<int:pk>/confirm/', views.confirm_booking, name='confirm_booking'),
    path('bookings/<int:pk>/reject/', views.reject_booking, name='reject_booking'),
    path('bookings/<int:pk>/check-in/', views.check_in_booking, name='check_in_booking'),
    path('bookings/<int:pk>/check-out/', views.check_out_booking, name='check_out_booking'),
    path('bookings/<int:pk>/update-status/', views.update_booking_status, name='update_booking_status'),
    path('bookings/<int:pk>/edit/', views.edit_booking, name='edit_booking'),
    path('bookings/<int:pk>/override-allocation/', views.manager_override_allocation, name='manager_override_allocation'),

    # Payments
    path('payments/initiate/<int:booking_id>/', views.initiate_payment, name='initiate_payment'),
    path('payments/success/', views.payment_success, name='payment_success'),
    path('payments/fail/', views.payment_fail, name='payment_fail'),
    path('payments/ipn/', views.ssl_ipn, name='ssl_ipn'),
    path('payments/history/', views.payment_history, name='payment_history'),
    path('payments/receipt/<int:payment_id>/', views.payment_receipt_detail, name='payment_receipt_detail'),
    path('payments/receipt/<str:transaction_id>/', views.payment_receipt, name='payment_receipt'),
    path('payments/receipt/<int:payment_id>/download/', views.payment_receipt_download, name='payment_receipt_download'),
    path('payments/receipt/<int:payment_id>/mark-cod-paid/', views.mark_cod_paid, name='mark_cod_paid'),

    # Complaints
    path('complaints/create/', views.create_complaint, name='create_complaint'),
    path('complaints/my/', views.my_complaints, name='my_complaints'),
    path('complaints/', views.complaint_list, name='complaint_list'),
    path('complaints/<int:pk>/', views.complaint_detail, name='complaint_detail'),
    path('complaints/<int:pk>/assign/', views.assign_complaint, name='assign_complaint'),
    path('complaints/<int:pk>/resolve/', views.resolve_complaint, name='resolve_complaint'),

    # Managers (Super Admin)
    path('managers/', views.manager_list, name='manager_list'),
    path('managers/add/', views.manager_add, name='manager_add'),
    path('managers/<int:pk>/edit/', views.manager_edit, name='manager_edit'),
    path('managers/<int:pk>/delete/', views.manager_delete, name='manager_delete'),

    # Notices
    path('notices/', views.notice_list, name='notice_list'),
    path('notices/create/', views.notice_create, name='notice_create'),
    path('notices/<int:pk>/edit/', views.notice_edit, name='notice_edit'),
    path('notices/<int:pk>/delete/', views.notice_delete, name='notice_delete'),

    # Visitors
    path('visitors/', views.visitor_list, name='visitor_list'),
    path('visitors/entry/', views.visitor_entry, name='visitor_entry'),
    path('visitors/<int:pk>/exit/', views.visitor_exit, name='visitor_exit'),

# Meals
    path('meals/', views.meal_dashboard, name='meal_dashboard'),
    path('meals/my-bills/', views.my_meal_bills, name='my_meal_bills'),
    path('meals/settings/', views.meal_settings_list, name='meal_settings_list'),
    path('meals/settings/<int:hostel_id>/', views.meal_settings_view, name='meal_settings'),
    path('meals/settings/<int:hostel_id>/toggle/', views.meal_service_toggle, name='meal_service_toggle'),
    path('meals/count/', views.meal_count, name='meal_count'),
    path('meals/payment-monitor/', views.meal_payment_monitor, name='meal_payment_monitor'),
    path('meals/bills/<int:pk>/mark-paid/', views.meal_bill_mark_paid, name='meal_bill_mark_paid'),
    path('meals/bills/<int:pk>/', views.meal_bill_detail, name='meal_bill_detail'),
    path('meals/bills/<int:pk>/pay/', views.meal_pay, name='meal_pay'),
    path('meals/pay-month/<int:year>/<int:month>/', views.meal_pay_month, name='meal_pay_month'),

    # Refunds
    path('refunds/', views.refund_list, name='refund_list'),
    path('refunds/<int:pk>/process/', views.process_refund, name='process_refund'),

    # Dashboards
    path('dashboard/', views.dashboard_home, name='dashboard_home'),
    path('dashboard/super-admin/', views.super_admin_dashboard, name='super_admin_dashboard'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/manager/', views.manager_dashboard, name='manager_dashboard'),
    path('dashboard/renter/', views.renter_dashboard, name='renter_dashboard'),

    # Reports
    path('reports/', views.report_index, name='report_index'),
    path('reports/bookings/', views.booking_report, name='booking_report'),
    path('reports/payments/', views.payment_report, name='payment_report'),
    path('reports/rooms/', views.room_report, name='room_report'),
    path('reports/complaints/', views.complaint_report, name='complaint_report'),
    path('reports/revenue/', views.revenue_report, name='revenue_report'),
    path('reports/export/pdf/<str:report_type>/', views.export_pdf, name='export_pdf'),
    path('reports/export/excel/<str:report_type>/', views.export_excel, name='export_excel'),
]
