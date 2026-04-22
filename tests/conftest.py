import pytest
import django
from django.conf import settings

def pytest_configure():
    if not settings.configured:
        settings.configure(
            SECRET_KEY='fake-key',
            DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': 'file:testdb?mode=memory&cache=shared'
                }
            },
            INSTALLED_APPS=[
                'django.contrib.contenttypes',
                'django.contrib.auth',
                'rest_framework',
                'adrf',
                'adrf_caching',
                'tests', 
            ],
            CACHES={
                'default': {
                    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                }
            },
            MIGRATION_MODULES={app: None for app in ['auth', 'contenttypes', 'tests', 'adrf_caching']},
        )
        django.setup()

@pytest.fixture(scope='session', autouse=True)
def setup_db(django_db_setup, django_db_blocker):
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
                    tables.append(table_name)