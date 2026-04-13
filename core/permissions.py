from django.db.models import Q
from core.models import Follow, Project


def can_view_project(user, project):
    """Check if user can view a project based on visibility."""
    if project.visibility == 'public':
        return True
    if not user or not user.is_authenticated:
        return False
    if project.owner_id == user.id:
        return True
    if project.visibility == 'friends':
        return _are_friends(user, project.owner)
    return False  # private


def _are_friends(user_a, user_b):
    """Mutual follow = friends."""
    if not user_a or not user_b:
        return False
    return (
        Follow.objects.filter(follower=user_a, following=user_b).exists()
        and Follow.objects.filter(follower=user_b, following=user_a).exists()
    )


def visible_projects_queryset(user):
    """Return a queryset of projects the user can see."""
    qs = Project.objects.all()
    if not user or not user.is_authenticated:
        return qs.filter(visibility='public')

    # User can see: public + own + friends-only where mutual follow
    friend_ids = list(
        Follow.objects.filter(follower=user).values_list('following_id', flat=True)
    )
    mutual_friend_ids = list(
        Follow.objects.filter(
            follower_id__in=friend_ids, following=user
        ).values_list('follower_id', flat=True)
    )

    return qs.filter(
        Q(visibility='public')
        | Q(owner=user)
        | Q(visibility='friends', owner_id__in=mutual_friend_ids)
    )
