from django.db import models


class IngestNotification(models.Model):
    """An ingest notification sent to the archive from the ingest_watchdog"""

    ingest_date = models.DateTimeField(auto_now_add=True)
    filename = models.CharField(max_length=1024)
    status = models.TextField(default="PENDING", editable=False)

    class Meta:
        ordering = ["-ingest_date"]


class IngestCount(models.Model):
    """An ingest path within the archive"""

    ingest_path = models.CharField(max_length=1024)
    count = models.IntegerField(default=0)
