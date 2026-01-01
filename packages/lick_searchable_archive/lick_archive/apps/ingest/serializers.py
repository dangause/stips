import logging

from rest_framework import serializers

from .models import IngestCount, IngestNotification

logger = logging.getLogger(__name__)


class IngestNotificationListSerializer(serializers.ListSerializer):
    """Custom list serializer class, to make sure batches of notifications
    are inserted in one transaction to help with performance.
    """

    def create(self, validated_data):
        """Custom create to use Django's bulk_create method when saving data.

        Args:
        validated_data (list): The validated list of notifications from
                               the client.
        """
        ingests = [IngestNotification(**item) for item in validated_data]
        return IngestNotification.objects.bulk_create(ingests)


class IngestNotificationSerializer(serializers.ModelSerializer):
    """Serializer for the IngestNotification model."""

    class Meta:
        model = IngestNotification
        filename = serializers.CharField(
            max_length=1024, allow_blank=False, trim_whitespace=True
        )
        fields = ["ingest_date", "filename", "status"]
        list_serializer_class = IngestNotificationListSerializer


class IngestCountsSerializer(serializers.ModelSerializer):
    """Serializer for the IngestNotification model."""

    class Meta:
        model = IngestCount
        fields = ["ingest_path", "count"]
