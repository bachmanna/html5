from rest_framework import serializers
from html5cda import models


class CodesystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Codesystem
        fields = '__all__'


class ScriptelementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Scriptelement
        fields = '__all__'


class HeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Header
        fields = '__all__'


class FooterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Footer
        fields = '__all__'


class ArticlehtmlSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Articlehtml
        fields = '__all__'


class CodeSerializer(serializers.ModelSerializer):
    codesystem = CodesystemSerializer(source='codesystem', many=False, read_only=True)
    class Meta:
        model = models.Code
        fields = ('id', 'code', 'displayname', 'codesystem', 'codesystem')


class EstudioSerializer(serializers.ModelSerializer):
    code = CodeSerializer(source="code", many=False, read_only=True)
    class Meta:
        model = models.Estudio
        fields = ('id', 'modalidad', 'code', 'code')


class PlantillaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Plantilla
        fields = '__all__'


class PlantillagruposldapSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Plantillagruposldap
        fields = '__all__'


class SeccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Seccion
        fields = '__all__'


class SelectoptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Selectoption
        fields = '__all__'


class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Entry
        fields = '__all__'


class QualifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Qualifier
        fields = '__all__'


class ValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Value
        fields = '__all__'


class AutenticadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Autenticado
        fields = '__all__'


class SecSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Sec
        fields = '__all__'


class SubsecSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Subsec
        fields = '__all__'


class SubsubsecSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Subsubsec
        fields = '__all__'


class FirmaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Firma
        fields = '__all__'


class SubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Submit
        fields = '__all__'