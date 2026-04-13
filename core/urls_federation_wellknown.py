from django.urls import path
from . import views_federation

urlpatterns = [
    path('', views_federation.well_known, name='federation-well-known'),
]
