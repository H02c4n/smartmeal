from django.core.management.base import BaseCommand

from apps.inventory import services


class Command(BaseCommand):
    help = "Release active stock reservations whose expiry time has passed (safe to repeat)."

    def handle(self, *args, **options):
        released = services.release_expired_reservations()
        self.stdout.write(f"Released {released} expired reservation(s).")
