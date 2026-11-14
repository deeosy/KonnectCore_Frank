import secrets

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

CSP_TEMPLATE = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "img-src 'self' data: https://unpkg.com https://tile.openstreetmap.org; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


class ContentSecurityPolicyMiddleware:
    """Send a Content-Security-Policy header with a fresh nonce on every request.

    Only the app's own files and <script> blocks carrying ``request.csp_nonce`` can run,
    so a script injected into a page (for example through a stored member name) is blocked.
    Inline style attributes stay allowed for now: they are lower risk and a few templates use them.
    """

    header = "Content-Security-Policy"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce
        response = self.get_response(request)
        if self.header not in response.headers:
            response.headers[self.header] = CSP_TEMPLATE.format(nonce=nonce)
        return response
