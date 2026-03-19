import pytest
import django
from django.conf import settings
from django.db import connection

def pytest_configure():
    if not settings.configured:
        settings.configure(
            SECRET_KEY='fake-key',
            DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                }
            },
            INSTALLED_APPS=[
                'django.contrib.contenttypes',
                'django.contrib.auth',
                'rest_framework',
                'adrf_caching',
                'tests', 
            ],
            CACHES={
                'default': {
                    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                }
            },
            # Игнорируем отсутствие файлов миграций
            MIGRATION_MODULES={
                'auth': None,
                'contenttypes': None,
                'tests': None,
            },
        )
        django.setup()

@pytest.fixture(scope='session', autouse=True)
def setup_db(django_db_setup, django_db_blocker):
    """Принудительно создаем только отсутствующие таблицы."""
    with django_db_blocker.unblock():
        from django.apps import apps
        from django.db import connection
        
        tables = connection.introspection.table_names()
        models = apps.get_models()
        
        with connection.schema_editor() as schema_editor:
            for model in models:
                table_name = model._meta.db_table
                if table_name not in tables:
                    schema_editor.create_model(model)
                    # Обновляем список таблиц, чтобы не пытаться создать индексы повторно
                    tables.append(table_name)