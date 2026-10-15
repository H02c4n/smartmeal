from rest_framework import serializers


class ReasonSerializer(serializers.Serializer):
    """Body of actions that must be justified (05 §1): stock reversal, lot release/block..."""

    reason = serializers.CharField(max_length=1000)
