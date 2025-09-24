from finance.models import Sale, SaleItem
from rest_framework import serializers

class SaleSerializer(serializers.ModelSerializer):
    class meta:
        model = Sale
        fields = '__all__'