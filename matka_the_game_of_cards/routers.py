class DatabaseRouter:
    """
    A router to control all database operations on models in the
    django_celery_beat and django_celery_results applications to SQLite,
    and all other operations to MongoDB.
    """
    route_app_labels = {'django_celery_beat', 'django_celery_results'}

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return 'sqlite'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return 'sqlite'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations if both are in the celery beat apps or neither
        if (
            obj1._meta.app_label in self.route_app_labels or
            obj2._meta.app_label in self.route_app_labels
        ):
            # Only allow relations within celery beat apps
            return obj1._meta.app_label in self.route_app_labels and obj2._meta.app_label in self.route_app_labels
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.route_app_labels:
            return db == 'sqlite'
        return db == 'default'
