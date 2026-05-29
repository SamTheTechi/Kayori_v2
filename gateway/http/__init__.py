from gateway.http.dashboard import register_dashboard_routes
from gateway.http.logs import register_logs_routes
from gateway.http.metrics import register_metrics_routes

__all__ = ["register_dashboard_routes", "register_logs_routes", "register_metrics_routes"]
