from django.conf import settings as django_settings


def nestora_context(request):
    ctx = {
        'nestora_name': 'Touch and Solve (TNS)',
        'nestora_tagline': 'Smart Living. Smarter Management.',
        'user_role': None,
        'user_name': None,
        'user_initial': None,
        'settings': {
            'NESTORA_CURRENCY': getattr(django_settings, 'NESTORA_CURRENCY', '৳'),
        },
    }
    if request.user.is_authenticated:
        ctx['user_role'] = request.user.role
        ctx['user_name'] = request.user.full_name
        ctx['user_initial'] = request.user.full_name[0].upper() if request.user.full_name else 'U'
    return ctx
