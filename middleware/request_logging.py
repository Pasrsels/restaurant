import time
from django.utils.deprecation import MiddlewareMixin
from loguru import logger


SENSITIVE_KEYS = {"password", "token", "csrfmiddlewaretoken"}


class RequestLoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._start_time = time.perf_counter()

    def process_response(self, request, response):
        try:
            duration_ms = None
            if hasattr(request, "_start_time"):
                duration_ms = int((time.perf_counter() - request._start_time) * 1000)

            user_repr = "anonymous"
            branch_repr = "-"
            try:
                if getattr(request, "user", None) and request.user.is_authenticated:
                    user_repr = request.user.username or str(request.user.id)
                    if getattr(request.user, "branch", None):
                        branch_repr = getattr(request.user.branch, "branch_name", "-")
            except Exception:
                pass

            method = request.method
            path = request.get_full_path()
            status = getattr(response, "status_code", "-")

            # Build safe query/body preview
            safe_params = {}
            try:
                if request.method == "GET":
                    for k, v in request.GET.items():
                        safe_params[k] = v if k not in SENSITIVE_KEYS else "***"
                else:
                    for k, v in request.POST.items():
                        safe_params[k] = v if k not in SENSITIVE_KEYS else "***"
            except Exception:
                safe_params = {}

            logger.info(
                "{method} {path} -> {status} | user={user} branch={branch} duration={duration}ms params={params}",
                method=method,
                path=path,
                status=status,
                user=user_repr,
                branch=branch_repr,
                duration=duration_ms,
                params=safe_params,
            )
        finally:
            return response

    def process_exception(self, request, exception):
        user_repr = "anonymous"
        try:
            if getattr(request, "user", None) and request.user.is_authenticated:
                user_repr = request.user.username or str(request.user.id)
        except Exception:
            pass
        logger.exception(
            "Unhandled exception in view | user={user} path={path}",
            user=user_repr,
            path=getattr(request, "path", "-"),
        )
        return None


