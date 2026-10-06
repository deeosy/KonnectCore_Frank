from django.utils.cache import add_never_cache_headers, patch_vary_headers


class NoStoreForAuthenticatedMiddleware:
    """Tell browsers not to keep copies of signed-in pages.

    Without this, pressing Back after signing out (for example on a shared phone)
    can show the last private page, such as member names and phone numbers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            add_never_cache_headers(response)
            patch_vary_headers(response, ("Cookie",))
        return response