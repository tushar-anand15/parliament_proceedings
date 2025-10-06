"""
URL configuration for parliament_api project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.http import JsonResponse
from django.shortcuts import redirect
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView


def home_redirect(request):
    """Redirect root URL to Swagger docs"""
    return redirect('/api/docs/')


def api_root(request):
    """API root endpoint with overview"""
    return JsonResponse({
        'message': 'Welcome to Parliament Proceedings API',
        'version': '1.0.0',
        'documentation': '/api/docs/',
        'redoc': '/api/redoc/',
        'endpoints': {
            'authentication': '/api/auth/',
            'questions': {
                'lok_sabha': '/api/questions/ls/',
                'rajya_sabha': '/api/questions/rs/'
            },
            'debates': '/api/debates/',
            'data_explorer': {
                'ls_questions': '/api/explorer/ls/questions/',
                'rs_questions': '/api/explorer/rs/questions/',
                'ls_debates': '/api/explorer/ls/debates/',
                'rs_debates': '/api/explorer/rs/debates/',
                'metadata': '/api/explorer/metadata/'
            },
            'scraper': '/api/scraper/',
            'files': '/api/files/',
            'ai_service': '/api/ai/',
            'admin': '/admin/'
        }
    })


urlpatterns = [
    # Root redirect
    path('', home_redirect, name='home'),
    
    # Admin interface
    path('admin/', admin.site.urls),
    
    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # API root
    path('api/', api_root, name='api-root'),
    
    # Service endpoints
    path('api/auth/', include('services.user_auth.urls')),
    path('api/questions/', include('services.questions.urls')),  # LS at /ls/, RS at /rs/
    path('api/scraper/', include('services.scraper.urls')),
    path('api/files/', include('services.files.urls')),
    path('api/ai/', include('services.ai_service.urls')),
    path('api/debates/', include('services.debates.urls')),
    path('api/explorer/', include('services.data_explorer.urls')),  # Data Explorer
]
