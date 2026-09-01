import base64
import os

from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from weasyprint import HTML as WeasyHTML

from .decorators import seller_or_admin, scanner_or_admin, admin_required
from .forms import (
    TicketCreateForm,
    UserCreateForm,
    UserEditForm,
    AdminPasswordChangeForm,
)
from .models import Ticket, ScanLog, UserProfile
from .utils import generate_qr_code_base64

ROLE_SELLER = 'seller'
ROLE_SCANNER = 'scanner'
ROLE_ADMIN = 'admin'


def _safe_redirect(request, fallback):
    """Redirect back where the user came from, but never off-site."""
    target = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER', '')
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback)


# ---------------------------------------------------------------- auth

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username'),
            password=request.POST.get('password'),
        )
        if user:
            login(request, user)
            return _safe_redirect(request, 'dashboard')
        messages.error(request, 'Invalid username or password.')

    return render(request, 'tickets/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# ---------------------------------------------------------------- dashboard

@login_required
def dashboard(request):
    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'Your account has no role assigned. Contact an administrator.')
        return render(request, 'tickets/dashboard.html', {})

    role = profile.role
    context = {'role': role}

    if role == ROLE_SELLER:
        mine = Ticket.objects.filter(created_by=request.user)
        counts = mine.aggregate(
            total=Count('id'),
            used=Count('id', filter=Q(status=Ticket.STATUS_USED)),
            unused=Count('id', filter=Q(status=Ticket.STATUS_UNUSED)),
        )
        context.update({
            'my_tickets': mine.order_by('-created_at')[:10],
            'total_created': counts['total'],
            'used_count': counts['used'],
            'unused_count': counts['unused'],
        })

    elif role == ROLE_SCANNER:
        my_scans = ScanLog.objects.filter(scanned_by=request.user)
        counts = my_scans.aggregate(
            total=Count('id'),
            valid=Count('id', filter=Q(result=ScanLog.RESULT_VALID)),
            invalid=Count('id', filter=Q(result__in=[
                ScanLog.RESULT_USED, ScanLog.RESULT_INVALID, ScanLog.RESULT_INACTIVE,
            ])),
        )
        context.update({
            'recent_scans': my_scans.select_related('ticket').order_by('-scanned_at')[:10],
            'total_scans': counts['total'],
            'valid_scans': counts['valid'],
            'invalid_scans': counts['invalid'],
        })

    elif role == ROLE_ADMIN:
        tickets = Ticket.objects.aggregate(
            total=Count('id'),
            used=Count('id', filter=Q(status=Ticket.STATUS_USED)),
            unused=Count('id', filter=Q(status=Ticket.STATUS_UNUSED)),
            inactive=Count('id', filter=Q(is_active=False)),
            early_bird=Count('id', filter=Q(ticket_type=Ticket.TYPE_EARLY_BIRD)),
            regular=Count('id', filter=Q(ticket_type=Ticket.TYPE_REGULAR)),
            vip=Count('id', filter=Q(ticket_type=Ticket.TYPE_VIP)),
        )
        scans = ScanLog.objects.aggregate(
            total=Count('id'),
            invalid=Count('id', filter=Q(result__in=[
                ScanLog.RESULT_INVALID, ScanLog.RESULT_INACTIVE,
            ])),
        )
        context.update({
            'total_tickets': tickets['total'],
            'used_tickets': tickets['used'],
            'unused_tickets': tickets['unused'],
            'inactive_tickets': tickets['inactive'],
            'early_bird_count': tickets['early_bird'],
            'regular_count': tickets['regular'],
            'vip_count': tickets['vip'],
            'total_scans': scans['total'],
            'invalid_scans': scans['invalid'],
            'total_users': User.objects.count(),
            'recent_scans': ScanLog.objects.select_related('ticket', 'scanned_by').order_by('-scanned_at')[:10],
            'recent_tickets': Ticket.objects.select_related('created_by').order_by('-created_at')[:10],
            'sellers': User.objects.filter(profile__role=ROLE_SELLER).annotate(
                ticket_count=Count('created_tickets')
            ),
        })

    return render(request, 'tickets/dashboard.html', context)


# ---------------------------------------------------------------- seller

@login_required
@seller_or_admin
def create_ticket(request):
    if request.method == 'POST':
        form = TicketCreateForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.created_by = request.user
            ticket.save()
            messages.success(request, f'Ticket created successfully! ID: {ticket.short_id}')
            return redirect('ticket_detail', pk=ticket.pk)
    else:
        form = TicketCreateForm()
    return render(request, 'tickets/create_ticket.html', {'form': form})


@login_required
@seller_or_admin
def my_tickets(request):
    if request.user.profile.role == ROLE_ADMIN:
        tickets = Ticket.objects.select_related('created_by', 'validated_by')
    else:
        tickets = Ticket.objects.filter(created_by=request.user).select_related('validated_by')

    status_filter = request.GET.get('status', '')
    if status_filter in (Ticket.STATUS_USED, Ticket.STATUS_UNUSED):
        tickets = tickets.filter(status=status_filter)

    return render(request, 'tickets/my_tickets.html', {
        'tickets': tickets.order_by('-created_at'),
        'status_filter': status_filter,
    })


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    profile = getattr(request.user, 'profile', None)
    if profile and profile.role == ROLE_SELLER and ticket.created_by != request.user:
        messages.error(request, "You can only view your own tickets.")
        return redirect('my_tickets')

    return render(request, 'tickets/ticket_detail.html', {
        'ticket': ticket,
        'scan_logs': ticket.scan_logs.select_related('scanned_by').order_by('-scanned_at'),
        'qr_b64': generate_qr_code_base64(ticket.token),
    })


# ---------------------------------------------------------------- scanner

@login_required
@scanner_or_admin
def scan_ticket(request):
    context = {}
    if request.method == 'POST':
        token = request.POST.get('ticket_token', '').strip()
        context['scan_result'] = validate_ticket_token(token, request.user)
    return render(request, 'tickets/scan_ticket.html', context)


def validate_ticket_token(token, user):
    if not token:
        ScanLog.objects.create(
            scanned_by=user, result=ScanLog.RESULT_INVALID,
            raw_data='', notes='Empty token submitted',
        )
        return {'result': ScanLog.RESULT_INVALID, 'message': 'No ticket data received.', 'ticket': None}

    try:
        ticket = Ticket.objects.get(token=token)
    except Ticket.DoesNotExist:
        ScanLog.objects.create(
            scanned_by=user, result=ScanLog.RESULT_INVALID,
            raw_data=token, notes='Token not found in database',
        )
        return {
            'result': ScanLog.RESULT_INVALID,
            'message': 'Ticket not found. It may be forged or tampered.',
            'ticket': None,
        }

    if not ticket.is_active:
        ScanLog.objects.create(
            scanned_by=user, ticket=ticket, result=ScanLog.RESULT_INACTIVE, raw_data=token,
        )
        return {
            'result': ScanLog.RESULT_INACTIVE,
            'message': 'This ticket has been deactivated.',
            'ticket': ticket,
        }

    if ticket.is_used:
        ScanLog.objects.create(
            scanned_by=user, ticket=ticket, result=ScanLog.RESULT_USED, raw_data=token,
        )
        return {
            'result': ScanLog.RESULT_USED,
            'message': 'This ticket has already been used.',
            'ticket': ticket,
            'first_scan': ticket.validated_at,
            'first_scanner': ticket.validated_by,
        }

    # Valid — mark as used.
    ticket.status = Ticket.STATUS_USED
    ticket.validated_at = timezone.now()
    ticket.validated_by = user
    ticket.save(update_fields=['status', 'validated_at', 'validated_by'])
    ScanLog.objects.create(
        scanned_by=user, ticket=ticket, result=ScanLog.RESULT_VALID, raw_data=token,
    )
    return {'result': ScanLog.RESULT_VALID, 'message': 'Ticket is valid. Entry granted!', 'ticket': ticket}


# ---------------------------------------------------------------- admin: tickets

@login_required
@admin_required
def ticket_management(request):
    tickets = Ticket.objects.select_related('created_by', 'validated_by')
    status_filter = request.GET.get('status', '')
    active_filter = request.GET.get('active', '')
    search = request.GET.get('search', '').strip()
    seller_filter = request.GET.get('seller', '')
    search = request.GET.get('search', '').strip()

    if seller_filter.isdigit():
        tickets = tickets.filter(created_by_id=int(seller_filter))
    if status_filter in (Ticket.STATUS_USED, Ticket.STATUS_UNUSED):
        tickets = tickets.filter(status=status_filter)
    if active_filter == 'active':
        tickets = tickets.filter(is_active=True)
    elif active_filter == 'inactive':
        tickets = tickets.filter(is_active=False)
    if search:
        tickets = tickets.filter(
            Q(purchaser_name__icontains=search) |
            Q(ticket_id__icontains=search) |
            Q(purchaser_email__icontains=search) |
            Q(purchaser_phone__icontains=search)
        )

    return render(request, 'tickets/ticket_management.html', {
        'tickets': tickets.order_by('-created_at'),
        'status_filter': status_filter,
        'active_filter': active_filter,
        'search': search,
        'seller_filter': seller_filter,
    })


@login_required
@admin_required
def toggle_ticket_active(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    ticket.is_active = not ticket.is_active
    ticket.save(update_fields=['is_active'])
    state = 'activated' if ticket.is_active else 'deactivated'
    messages.success(request, f'Ticket {ticket.short_id} has been {state}.')
    return _safe_redirect(request, 'ticket_management')


@login_required
@admin_required
def delete_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method != 'POST':
        messages.error(request, 'Deletion must be confirmed from the ticket list.')
        return redirect('ticket_management')

    if ticket.is_active:
        messages.error(
            request,
            f'Ticket {ticket.short_id} is still active. Deactivate it first, then delete.',
        )
        return redirect('ticket_management')

    short_id, name = ticket.short_id, ticket.purchaser_name
    # ScanLog.ticket is SET_NULL, so scan history survives as an orphaned record.
    ticket.delete()
    messages.success(request, f'Ticket {short_id} ({name}) was permanently deleted.')
    return redirect('ticket_management')


# ---------------------------------------------------------------- admin: users

@login_required
@admin_required
def user_management(request):
    search = request.GET.get('search', '').strip()
    role_filter = request.GET.get('role', '')

    users = User.objects.select_related('profile').annotate(
        ticket_count=Count('created_tickets'),
    )
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    if role_filter in (ROLE_SELLER, ROLE_SCANNER, ROLE_ADMIN):
        users = users.filter(profile__role=role_filter)

    return render(request, 'tickets/user_management.html', {
        'users': users.order_by('username'),
        'search': search,
        'role_filter': role_filter,
    })


@login_required
@admin_required
def user_tickets(request, pk):
    seller = get_object_or_404(User.objects.select_related('profile'), pk=pk)
    all_tickets = Ticket.objects.filter(created_by=seller)

    stats = all_tickets.aggregate(
        total=Count('id'),
        used=Count('id', filter=Q(status=Ticket.STATUS_USED)),
        unused=Count('id', filter=Q(status=Ticket.STATUS_UNUSED)),
        inactive=Count('id', filter=Q(is_active=False)),
        early_bird=Count('id', filter=Q(ticket_type=Ticket.TYPE_EARLY_BIRD)),
        regular=Count('id', filter=Q(ticket_type=Ticket.TYPE_REGULAR)),
        vip=Count('id', filter=Q(ticket_type=Ticket.TYPE_VIP)),
    )

    tickets = all_tickets.select_related('validated_by')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    search = request.GET.get('search', '').strip()

    if status_filter in (Ticket.STATUS_USED, Ticket.STATUS_UNUSED):
        tickets = tickets.filter(status=status_filter)
    if type_filter in (Ticket.TYPE_EARLY_BIRD, Ticket.TYPE_REGULAR, Ticket.TYPE_VIP):
        tickets = tickets.filter(ticket_type=type_filter)
    if search:
        tickets = tickets.filter(
            Q(purchaser_name__icontains=search) |
            Q(ticket_id__icontains=search) |
            Q(purchaser_email__icontains=search) |
            Q(purchaser_phone__icontains=search)
        )

    return render(request, 'tickets/user_tickets.html', {
        'seller': seller,
        'tickets': tickets.order_by('-created_at'),
        'stats': stats,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search': search,
    })


@login_required
@admin_required
def create_user(request):
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data['role']
            UserProfile.objects.update_or_create(user=user, defaults={'role': role})
            messages.success(request, f'User {user.username} created with role {role}.')
            return redirect('user_management')
    else:
        form = UserCreateForm()
    return render(request, 'tickets/create_user.html', {'form': form})


@login_required
@admin_required
def edit_user(request, pk):
    edited_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=edited_user)
        if form.is_valid():
            form.save()
            UserProfile.objects.update_or_create(
                user=edited_user, defaults={'role': form.cleaned_data['role']},
            )
            messages.success(request, f'User {edited_user.username} updated.')
            return redirect('user_management')
    else:
        form = UserEditForm(instance=edited_user)

    return render(request, 'tickets/edit_user.html', {'form': form, 'edited_user': edited_user})


@login_required
@admin_required
def change_user_password(request, pk):
    target_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = AdminPasswordChangeForm(request.POST)
        if form.is_valid():
            target_user.set_password(form.cleaned_data['password1'])
            target_user.save(update_fields=['password'])

            if target_user.pk == request.user.pk:
                # Keep the admin signed in after changing their own password.
                update_session_auth_hash(request, target_user)
                messages.success(request, 'Your password has been updated.')
            else:
                messages.success(
                    request,
                    f'Password for {target_user.username} has been reset. '
                    f'They will need to log in again with the new password.',
                )
            return redirect('user_management')
    else:
        form = AdminPasswordChangeForm()

    return render(request, 'tickets/change_password.html', {
        'form': form,
        'target_user': target_user,
    })


# ---------------------------------------------------------------- admin: reports

@login_required
@admin_required
def reports(request):
    totals = Ticket.objects.aggregate(
        total=Count('id'),
        used=Count('id', filter=Q(status=Ticket.STATUS_USED)),
        unused=Count('id', filter=Q(status=Ticket.STATUS_UNUSED)),
        inactive=Count('id', filter=Q(is_active=False)),
    )

    scan_data = {
        row['result']: row['count']
        for row in ScanLog.objects.values('result').annotate(count=Count('id'))
    }

    sellers = User.objects.filter(profile__role=ROLE_SELLER).annotate(
        tickets_created=Count('created_tickets'),
        used_tickets=Count('created_tickets', filter=Q(created_tickets__status=Ticket.STATUS_USED)),
    ).order_by('-tickets_created')

    scanners = User.objects.filter(profile__role=ROLE_SCANNER).annotate(
        total_scans=Count('scanlog'),
        valid_scans=Count('scanlog', filter=Q(scanlog__result=ScanLog.RESULT_VALID)),
    ).order_by('-total_scans')

    return render(request, 'tickets/reports.html', {
        'total': totals['total'],
        'used': totals['used'],
        'unused': totals['unused'],
        'inactive': totals['inactive'],
        'scan_data': scan_data,
        'sellers': sellers,
        'scanners': scanners,
        'recent_logs': ScanLog.objects.select_related('ticket', 'scanned_by').order_by('-scanned_at')[:50],
    })


# ---------------------------------------------------------------- pdf

@login_required
def ticket_pdf(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    profile = getattr(request.user, 'profile', None)
    if profile and profile.role == ROLE_SELLER and ticket.created_by != request.user:
        messages.error(request, "You can only print your own tickets.")
        return redirect('my_tickets')

    logo_b64 = ''
    base_dir = os.path.dirname(os.path.dirname(__file__))
    for ext in ('png', 'jpg', 'jpeg'):
        logo_path = os.path.join(base_dir, 'static', 'images', f'logo.{ext}')
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as fh:
                logo_b64 = base64.b64encode(fh.read()).decode()
            break

    html_string = render_to_string('tickets/ticket_pdf.html', {
        'ticket': ticket,
        'qr_b64': generate_qr_code_base64(ticket.token),
        'logo_b64': logo_b64,
    })

    response = HttpResponse(WeasyHTML(string=html_string).write_pdf(), content_type='application/pdf')
    response['Content-Disposition'] = f'filename="LANESRA-Ticket-{ticket.short_id}.pdf"'
    return response