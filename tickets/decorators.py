from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not hasattr(request.user, 'profile') or request.user.profile.role not in roles:
                messages.error(request, "You don't have permission to access that page.")
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def seller_or_admin(view_func):
    return role_required('seller', 'admin')(view_func)


def scanner_or_admin(view_func):
    return role_required('scanner', 'admin')(view_func)


def admin_required(view_func):
    return role_required('admin')(view_func)
