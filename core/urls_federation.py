from django.urls import path
from . import views_federation

urlpatterns = [
    # Public metadata
    path('projects/', views_federation.public_projects, name='federation-projects'),
    path('projects/<int:project_id>/prompts/', views_federation.public_project_prompts, name='federation-project-prompts'),

    # Pairing protocol
    path('pair/request/', views_federation.pair_request, name='federation-pair-request'),
    path('pair/accept/', views_federation.pair_accept, name='federation-pair-accept'),
    path('pair/confirm/', views_federation.pair_confirm, name='federation-pair-confirm'),

    # Server management (admin)
    path('servers/add/', views_federation.add_server, name='federation-add-server'),
    path('servers/action/', views_federation.server_action, name='federation-server-action'),

    # Subscriptions
    path('subscribe/', views_federation.subscribe, name='federation-subscribe'),
    path('unsubscribe/', views_federation.unsubscribe, name='federation-unsubscribe'),

    # Push sync (from remote)
    path('push/prompts/', views_federation.push_prompts, name='federation-push-prompts'),
    path('push/comment/', views_federation.push_comment, name='federation-push-comment'),

    # Status / Explore
    path('status/', views_federation.federation_status, name='federation-status'),
    path('explore/<int:server_id>/', views_federation.explore_server, name='federation-explore-server'),
]
