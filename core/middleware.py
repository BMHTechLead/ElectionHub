import re
from django.conf import settings
from django.shortcuts import redirect

class ForceLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.ignore_paths = [re.compile(p) for p in getattr(settings, 'LOGIN_REQUIRED_IGNORE_PATHS', [])]

    def __call__(self, request):

        if not request.user.is_authenticated:
            path = request.path_info
            if not any(p.match(path) for p in self.ignore_paths):
                return redirect(settings.LOGIN_URL)

        return self.get_response(request)
