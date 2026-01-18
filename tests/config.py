import django
from django.conf import settings
from django.core.management import call_command

urlpatterns = []

def setup_django():
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "django.contrib.sessions",
                "rest_framework",
                "adrf",
                "adrf_caching",
            ],
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                }
            },
            SECRET_KEY="fake-key-for-testing",
            AUTH_USER_MODEL="auth.User",
            ROOT_URLCONF=__name__, 
        )
        django.setup()
        call_command("migrate", verbosity=0)

setup_django()