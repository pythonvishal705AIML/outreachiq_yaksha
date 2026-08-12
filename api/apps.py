# from django.apps import AppConfig
#
#
# class ApiConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'api'
from django.apps import AppConfig
import threading
import logging

logger = logging.getLogger(__name__)

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        def _warm_normalizer():
            try:
                from api.normalization.filter_normalizer import get_normalizer
                logger.info("[STARTUP] Pre-warming SearchFilterNormalizer singleton...")
                get_normalizer()
                logger.info("[STARTUP] SearchFilterNormalizer singleton ready.")
            except Exception as e:
                logger.warning(f"[STARTUP] Normalizer pre-warm failed: {e}")

        thread = threading.Thread(target=_warm_normalizer, daemon=True)
        thread.start()