from datetime import timedelta
from django.utils import timezone
from .models import UserReward


def check_daily_login_reward(user):
    if not user or not user.is_authenticated:
        return {'claimed': False, 'points_added': 0, 'streak_day': 0}

    reward, _ = UserReward.objects.get_or_create(user=user)
    today = timezone.localdate()

    if reward.last_login_date == today:
        return {'claimed': False, 'points_added': 0, 'streak_day': reward.streak_days or 1, 'already_claimed': True}

    if reward.last_login_date == today - timedelta(days=1):
        # Consecutive day: increment streak in 1 to 7 cycle
        new_streak = (reward.streak_days % 7) + 1
    else:
        # Missed a day or first time
        new_streak = 1

    points_awarded = new_streak
    reward.points += points_awarded
    reward.total_points_earned += points_awarded
    reward.streak_days = new_streak
    reward.last_login_date = today
    reward.save()

    return {
        'claimed': True,
        'points_added': points_awarded,
        'streak_day': new_streak,
        'total_points': reward.points,
        'already_claimed': False
    }


def user_rewards_context(request):
    if request.user.is_authenticated:
        reward, _ = UserReward.objects.get_or_create(user=request.user)
        # Check daily login streak bonus
        daily_info = check_daily_login_reward(request.user)
        return {
            'user_reward': reward,
            'daily_bonus_info': daily_info,
        }
    return {
        'user_reward': None,
        'daily_bonus_info': {'claimed': False, 'points_added': 0, 'streak_day': 0},
    }
