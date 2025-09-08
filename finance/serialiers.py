from rest_framework import serializers
from finance.models import *

class ChangeSerializer(serializers.ModelSerializer):
    class meta:
        models = Change
        fields = '__all__'