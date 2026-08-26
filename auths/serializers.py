from .models import User
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label="Confirm password")

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "password2"]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, data):
        if data["password"] != data["password2"]:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop("password2")
        
        from django.apps import apps
        from django.utils import timezone
        terms_version = "v1.0"
        try:
            PolicyVersion = apps.get_model('policies', 'PolicyVersion')
            PolicyDocument = apps.get_model('policies', 'PolicyDocument')
            latest_terms = PolicyVersion.objects.filter(
                document__doc_type=PolicyDocument.DocType.TERMS_OF_SERVICE,
                document__is_published=True
            ).order_by('-created_at').first()
            if latest_terms:
                terms_version = latest_terms.version_number
        except Exception:
            pass

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            terms_accepted=True,
            terms_accepted_version=terms_version,
            terms_accepted_date=timezone.now(),
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    token = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = User
        fields = [
            'id', 'username', 'email',
            'first_name', 'last_name',
            'is_staff', 'token', 'is_superuser'
        ]

    def get_token(self, obj):
        token = RefreshToken.for_user(obj)
        return str(token.access_token)
