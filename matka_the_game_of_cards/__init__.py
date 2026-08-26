# Monkey patch django-mongodb-backend to allow MongoDB 5.0+
try:
    from django_mongodb_backend.features import DatabaseFeatures
    DatabaseFeatures.minimum_database_version = (5, 0)
except ImportError:
    pass

# Patch Django REST Framework to map MongoDB ObjectId fields to CharField
try:
    from rest_framework import serializers
    from django_mongodb_backend.fields import ObjectIdAutoField, ObjectIdField
    serializers.ModelSerializer.serializer_field_mapping[ObjectIdAutoField] = serializers.CharField
    serializers.ModelSerializer.serializer_field_mapping[ObjectIdField] = serializers.CharField
except ImportError:
    pass

# Patch JSONEncoder to support MongoDB ObjectId and Decimal128 serialization
try:
    from rest_framework.utils.encoders import JSONEncoder
    from bson import ObjectId
    from bson.decimal128 import Decimal128

    original_default = JSONEncoder.default

    def patched_default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, Decimal128):
            return str(obj.to_decimal())
        return original_default(self, obj)

    JSONEncoder.default = patched_default
except Exception:
    pass

