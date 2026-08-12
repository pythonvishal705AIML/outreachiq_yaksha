# from django.apps import AppConfig
#
# class AgentRuntimeConfig(AppConfig):
#     default_auto_field = "django.db.models.BigAutoField"
#     name = "agent_runtime"


import logging

from django.apps import AppConfig


class AgentRuntimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "agent_runtime"

    def ready(self):
        # Ensure all agent_runtime.* loggers print to console
        rt_logger = logging.getLogger("agent_runtime")
        if not rt_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("[%(name)s] %(levelname)s %(message)s")
            )
            rt_logger.addHandler(handler)
        rt_logger.setLevel(logging.DEBUG)