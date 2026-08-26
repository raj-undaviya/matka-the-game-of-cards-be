"""
URL configuration for matka project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from auths.views import serve_policy_file

urlpatterns = [
    path('admin/', admin.site.urls),
    path('terms.html', serve_policy_file, {'filename': 'terms.html'}, name='terms_html'),
    path('privacy.html', serve_policy_file, {'filename': 'privacy.html'}, name='privacy_html'),
    path('api/auth/', include('auths.urls')),  
    path('api/wallet/', include('wallet.urls')),
    path('api/game/', include('game.urls')),
    path("api/admin/", include('servers.urls')),  # ← yeh add karo
    path("api/policies/", include('policies.urls')),  # ← yeh add karo
]
