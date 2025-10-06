"""
Data Explorer URL Configuration
"""
from django.urls import path
from . import views

app_name = 'data_explorer'

urlpatterns = [
    # Lok Sabha Questions Explorer
    path('ls/questions/', views.LSQuestionExplorerView.as_view(), name='ls-questions-explorer'),
    path('ls/questions/<int:pk>/', views.QuestionDetailView.as_view(), name='ls-question-detail'),
    
    # Rajya Sabha Questions Explorer
    path('rs/questions/', views.RSQuestionExplorerView.as_view(), name='rs-questions-explorer'),
    path('rs/questions/<int:pk>/', views.QuestionDetailView.as_view(), name='rs-question-detail'),
    
    # Lok Sabha Debates Explorer
    path('ls/debates/', views.LSDebateExplorerView.as_view(), name='ls-debates-explorer'),
    path('ls/debates/<int:pk>/', views.DebateDetailView.as_view(), name='ls-debate-detail'),
    
    # Rajya Sabha Debates Explorer
    path('rs/debates/', views.RSDebateExplorerView.as_view(), name='rs-debates-explorer'),
    path('rs/debates/<int:pk>/', views.DebateDetailView.as_view(), name='rs-debate-detail'),
    
    # Metadata Endpoints (for filter options)
    path('metadata/questions/', views.QuestionMetadataView.as_view(), name='questions-metadata'),
    path('metadata/debates/', views.DebateMetadataView.as_view(), name='debates-metadata'),
]
