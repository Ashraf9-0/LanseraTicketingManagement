import os
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from tickets.models import UserProfile


class Command(BaseCommand):
    help = "Create (or update) the admin superuser from ADMIN_USERNAME/ADMIN_EMAIL/ADMIN_PASSWORD env vars. Safe to run on every deploy."

    def handle(self, *args, **options):
        username = os.environ.get('ADMIN_USERNAME')
        email = os.environ.get('ADMIN_EMAIL', '')
        password = os.environ.get('ADMIN_PASSWORD')

        if not username or not password:
            self.stdout.write(self.style.WARNING(
                'ADMIN_USERNAME or ADMIN_PASSWORD not set — skipping admin creation.'
            ))
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True},
        )

        if created:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created superuser "{username}".'))
        else:
            self.stdout.write(self.style.NOTICE(f'Superuser "{username}" already exists — leaving password unchanged.'))

        profile, profile_created = UserProfile.objects.get_or_create(
            user=user, defaults={'role': 'admin'}
        )
        if not profile_created and profile.role != 'admin':
            profile.role = 'admin'
            profile.save()
            self.stdout.write(self.style.SUCCESS(f'Updated "{username}" profile role to admin.'))
        elif profile_created:
            self.stdout.write(self.style.SUCCESS(f'Created admin profile for "{username}".'))