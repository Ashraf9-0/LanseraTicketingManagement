from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.http import JsonResponse
from .models import Ticket, ScanLog, UserProfile
from .forms import TicketCreateForm, UserCreateForm, UserEditForm
from .utils import generate_qr_code_base64
from .decorators import seller_or_admin, scanner_or_admin, admin_required
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML as WeasyHTML
import base64, os
import json


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        messages.error(request, 'Invalid username or password.')
    return render(request, 'tickets/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'Your account has no role assigned. Contact an administrator.')
        return render(request, 'tickets/dashboard.html', {})

    role = profile.role
    context = {'role': role}

    if role == 'seller':
        my_tickets = Ticket.objects.filter(created_by=request.user).order_by('-created_at')
        context['my_tickets'] = my_tickets[:10]
        context['total_created'] = my_tickets.count()
        context['used_count'] = my_tickets.filter(status='used').count()
        context['unused_count'] = my_tickets.filter(status='unused').count()

    elif role == 'scanner':
        my_scans = ScanLog.objects.filter(scanned_by=request.user).order_by('-scanned_at')
        context['recent_scans'] = my_scans[:10]
        context['total_scans'] = my_scans.count()
        context['valid_scans'] = my_scans.filter(result='valid').count()
        context['invalid_scans'] = my_scans.filter(result__in=['already_used', 'invalid', 'inactive']).count()

    elif role == 'admin':
        context['total_tickets'] = Ticket.objects.count()
        context['used_tickets'] = Ticket.objects.filter(status='used').count()
        context['unused_tickets'] = Ticket.objects.filter(status='unused').count()
        context['inactive_tickets'] = Ticket.objects.filter(is_active=False).count()
        context['total_scans'] = ScanLog.objects.count()
        context['invalid_scans'] = ScanLog.objects.filter(result__in=['invalid', 'inactive']).count()
        context['total_users'] = User.objects.count()
        context['recent_scans'] = ScanLog.objects.select_related('ticket', 'scanned_by').order_by('-scanned_at')[:10]
        context['recent_tickets'] = Ticket.objects.select_related('created_by').order_by('-created_at')[:10]
        context['sellers'] = User.objects.filter(profile__role='seller').annotate(
            ticket_count=Count('created_tickets')
        )
        context['early_bird_count'] = Ticket.objects.filter(ticket_type='early_bird').count()
        context['regular_count'] = Ticket.objects.filter(ticket_type='regular').count()
        context['vip_count'] = Ticket.objects.filter(ticket_type='vip').count()

    return render(request, 'tickets/dashboard.html', context)

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
    if request.user.profile.role == 'admin':
        tickets = Ticket.objects.select_related('created_by', 'validated_by').order_by('-created_at')
    else:
        tickets = Ticket.objects.filter(created_by=request.user).select_related('validated_by').order_by('-created_at')

    status_filter = request.GET.get('status', '')
    if status_filter in ['used', 'unused']:
        tickets = tickets.filter(status=status_filter)

    return render(request, 'tickets/my_tickets.html', {'tickets': tickets, 'status_filter': status_filter})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    profile = getattr(request.user, 'profile', None)
    if profile and profile.role == 'seller' and ticket.created_by != request.user:
        messages.error(request, "You can only view your own tickets.")
        return redirect('my_tickets')
    scan_logs = ticket.scan_logs.select_related('scanned_by').order_by('-scanned_at')
    qr_b64 = generate_qr_code_base64(ticket.token)
    return render(request, 'tickets/ticket_detail.html', {'ticket': ticket, 'scan_logs': scan_logs, 'qr_b64': qr_b64})


@login_required
@scanner_or_admin
def scan_ticket(request):
    context = {}
    if request.method == 'POST':
        token = request.POST.get('ticket_token', '').strip()
        result_data = validate_ticket_token(token, request.user)
        context['scan_result'] = result_data
    return render(request, 'tickets/scan_ticket.html', context)


def validate_ticket_token(token, user):
    if not token:
        ScanLog.objects.create(scanned_by=user, result='invalid', raw_data='', notes='Empty token submitted')
        return {'result': 'invalid', 'message': 'No ticket data received.', 'ticket': None}

    try:
        ticket = Ticket.objects.get(token=token)
    except Ticket.DoesNotExist:
        ScanLog.objects.create(scanned_by=user, result='invalid', raw_data=token, notes='Token not found in database')
        return {'result': 'invalid', 'message': 'Ticket not found. It may be forged or tampered.', 'ticket': None}

    if not ticket.is_active:
        ScanLog.objects.create(scanned_by=user, ticket=ticket, result='inactive', raw_data=token)
        return {'result': 'inactive', 'message': 'This ticket has been deactivated.', 'ticket': ticket}

    if ticket.is_used:
        ScanLog.objects.create(scanned_by=user, ticket=ticket, result='already_used', raw_data=token)
        return {
            'result': 'already_used',
            'message': 'This ticket has already been used.',
            'ticket': ticket,
            'first_scan': ticket.validated_at,
            'first_scanner': ticket.validated_by,
        }

    # Valid! Mark as used.
    ticket.status = Ticket.STATUS_USED
    ticket.validated_at = timezone.now()
    ticket.validated_by = user
    ticket.save()
    ScanLog.objects.create(scanned_by=user, ticket=ticket, result='valid', raw_data=token)
    return {'result': 'valid', 'message': 'Ticket is valid. Entry granted!', 'ticket': ticket}


@login_required
@admin_required
def ticket_management(request):
    tickets = Ticket.objects.select_related('created_by', 'validated_by').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    active_filter = request.GET.get('active', '')
    search = request.GET.get('search', '')

    if status_filter in ['used', 'unused']:
        tickets = tickets.filter(status=status_filter)
    if active_filter == 'active':
        tickets = tickets.filter(is_active=True)
    elif active_filter == 'inactive':
        tickets = tickets.filter(is_active=False)
    if search:
        tickets = tickets.filter(
            Q(purchaser_name__icontains=search) |
            Q(ticket_id__icontains=search) |
            Q(purchaser_email__icontains=search)
        )

    return render(request, 'tickets/ticket_management.html', {
        'tickets': tickets,
        'status_filter': status_filter,
        'active_filter': active_filter,
        'search': search,
    })


@login_required
@admin_required
def toggle_ticket_active(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    ticket.is_active = not ticket.is_active
    ticket.save()
    state = 'activated' if ticket.is_active else 'deactivated'
    messages.success(request, f'Ticket {ticket.short_id} has been {state}.')
    return redirect(request.META.get('HTTP_REFERER', 'ticket_management'))


@login_required
@admin_required
def user_management(request):
    users = User.objects.select_related('profile').order_by('username')
    return render(request, 'tickets/user_management.html', {'users': users})


@login_required
@admin_required
def create_user(request):
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data['role']
            UserProfile.objects.create(user=user, role=role)
            messages.success(request, f'User {user.username} created with role {role}.')
            return redirect('user_management')
    else:
        form = UserCreateForm()
    return render(request, 'tickets/create_user.html', {'form': form})


@login_required
@admin_required
def edit_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            role = form.cleaned_data['role']
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save()
            messages.success(request, f'User {user.username} updated.')
            return redirect('user_management')
    else:
        form = UserEditForm(instance=user)
        if hasattr(user, 'profile'):
            form.fields['role'].initial = user.profile.role
    return render(request, 'tickets/edit_user.html', {'form': form, 'edited_user': user})


@login_required
@admin_required
def reports(request):
    total = Ticket.objects.count()
    used = Ticket.objects.filter(status='used').count()
    unused = Ticket.objects.filter(status='unused').count()
    inactive = Ticket.objects.filter(is_active=False).count()

    scans_by_result = ScanLog.objects.values('result').annotate(count=Count('id'))
    scan_data = {s['result']: s['count'] for s in scans_by_result}

    sellers = User.objects.filter(profile__role='seller').annotate(
        tickets_created=Count('created_tickets'),
        used_tickets=Count('created_tickets', filter=Q(created_tickets__status='used')),
    ).order_by('-tickets_created')

    scanner_qs = User.objects.filter(profile__role='scanner')
    scanners = []
    for sc in scanner_qs:
        logs = ScanLog.objects.filter(scanned_by=sc)
        sc.total_scans = logs.count()
        sc.valid_scans = logs.filter(result='valid').count()
        scanners.append(sc)
    scanners.sort(key=lambda x: x.total_scans, reverse=True)

    recent_logs = ScanLog.objects.select_related('ticket', 'scanned_by').order_by('-scanned_at')[:50]

    return render(request, 'tickets/reports.html', {
        'total': total, 'used': used, 'unused': unused, 'inactive': inactive,
        'scan_data': scan_data, 'sellers': sellers, 'scanners': scanners,
        'recent_logs': recent_logs,
    })
    


@login_required
def ticket_pdf(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    profile = getattr(request.user, 'profile', None)
    if profile and profile.role == 'seller' and ticket.created_by != request.user:
        messages.error(request, "You can only print your own tickets.")
        return redirect('my_tickets')

    # Embed QR image as base64 so WeasyPrint can render it
    qr_b64 = generate_qr_code_base64(ticket.token)

    # Embed logo
    logo_b64 = ''
    base_dir = os.path.dirname(os.path.dirname(__file__))
    for ext in ['png', 'jpg', 'jpeg']:
        logo_path = os.path.join(base_dir, 'static', 'images', f'logo.{ext}')
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as f:
                logo_b64 = base64.b64encode(f.read()).decode()
            break

    html_string = render_to_string('tickets/ticket_pdf.html', {
        'ticket': ticket,
        'qr_b64': qr_b64,
        'logo_b64': logo_b64,
    })

    pdf_file = WeasyHTML(string=html_string).write_pdf()
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename="LANESRA-Ticket-{ticket.short_id}.pdf"'
    return response