from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles and request.user.role != 'SUPER_ADMIN':
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('dashboard_home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role not in ['SUPER_ADMIN']:
            messages.error(request, 'Admin access required.')
            return redirect('dashboard_home')
        return view_func(request, *args, **kwargs)
    return wrapper

def manager_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role not in ['SUPER_ADMIN', 'HOSTEL_MANAGER']:
            messages.error(request, 'Manager access required.')
            return redirect('dashboard_home')
        return view_func(request, *args, **kwargs)
    return wrapper

def renter_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role != 'RENTER':
            messages.error(request, 'Renter access required.')
            return redirect('dashboard_home')
        return view_func(request, *args, **kwargs)
    return wrapper
