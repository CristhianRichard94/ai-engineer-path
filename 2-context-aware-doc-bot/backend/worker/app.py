import os

from celery import Celery
from config import settings

# ponytail: filesystem-based broker/backend is a deliberate stopgap to avoid
# needing a hosted Redis. Known ceiling: single-machine only (no HA, workers
# must share this filesystem), and /tmp is ephemeral across restarts on
# platforms like Fly.io (in-flight/undelivered tasks and job results are
# lost on redeploy/restart). Upgrade path: swap back to a real broker
# (Redis, SQS, etc.) once scaling beyond one worker box or needing
# durability across restarts.
_broker_in = os.path.join(settings.celery_broker_dir, "in")
_broker_out = os.path.join(settings.celery_broker_dir, "out")
_broker_processed = os.path.join(settings.celery_broker_dir, "processed")
for _dir in (_broker_in, _broker_out, _broker_processed):
    os.makedirs(_dir, exist_ok=True)

celery = Celery("doc_bot", broker="filesystem://")
celery.conf.broker_transport_options = {
    "data_folder_in": _broker_in,
    "data_folder_out": _broker_out,
}
celery.conf.result_backend = "file://" + _broker_processed
celery.conf.task_track_started = True
celery.conf.imports = ("worker.tasks",)
