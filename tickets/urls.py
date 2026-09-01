from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Seller
    path('tickets/create/', views.create_ticket, name='create_ticket'),
    path('tickets/', views.my_tickets, name='my_tickets'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),

    # Scanner
    path('scan/', views.scan_ticket, name='scan_ticket'),

    # Admin
    path('admin-panel/tickets/', views.ticket_management, name='ticket_management'),
    path('admin-panel/tickets/<int:pk>/toggle/', views.toggle_ticket_active, name='toggle_ticket_active'),
    path('admin-panel/tickets/<int:pk>/delete/', views.delete_ticket, name='delete_ticket'),
    path('admin-panel/users/', views.user_management, name='user_management'),
    path('admin-panel/users/create/', views.create_user, name='create_user'),
    path('admin-panel/users/<int:pk>/edit/', views.edit_user, name='edit_user'),
    path('admin-panel/users/<int:pk>/password/', views.change_user_password, name='change_user_password'),
    path('admin-panel/reports/', views.reports, name='reports'),

    # PDF
    path('tickets/<int:pk>/pdf/', views.ticket_pdf, name='ticket_pdf'),
]
