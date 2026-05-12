"""Celery application configuration for Sales API Service."""
from celery import Celery
import logging
import os

logger = logging.getLogger(__name__)

# Celeryアプリケーション初期化
celery_app = Celery("ai_micro_sales")

# Broker/Backend設定（環境変数から取得）
broker_url = os.getenv("CELERY_BROKER_URL", "redis://:password@host.docker.internal:6379/1")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://:password@host.docker.internal:6379/2")

celery_app.conf.broker_url = broker_url
celery_app.conf.result_backend = result_backend

# 基本設定
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Tokyo",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3300,  # 55 minutes
)

logger.info(f"Celery initialized for Sales API: broker={broker_url}")


@celery_app.task(bind=True)
def debug_task(self):
    """デバッグ用タスク"""
    print(f"Request: {self.request!r}")
    return "Debug task executed successfully"
