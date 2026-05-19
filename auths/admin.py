from django.contrib import admin

from .models import User


class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'is_email_verified')
    search_fields = ('email', 'Phone_number')

admin.site.register(User, UserAdmin)