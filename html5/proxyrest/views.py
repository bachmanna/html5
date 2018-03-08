from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
import requests
import uuid
from proxyrest.models import SessionRest, TokenAccessPatient
from html5dicom.models import Institution, Role, Setting
from proxyrest.serializers import TokenAccessPatientSerializer, SessionRestSerializer
from django.contrib.sessions.backends.db import SessionStore


@api_view(['POST'])
def rest_login(request, *args, **kwargs):
    if 'institution' in request.data and 'user' in request.data and 'password' in request.data:
        try:
            institution = Institution.objects.get(short_name=request.data.get('institution'))
        except Institution.DoesNotExist:
            return Response({'error': 'institution does not exist'}, status=status.HTTP_401_UNAUTHORIZED)
        user = authenticate(username=request.data.get('user'), password=request.data.get('password'))
        if user:
            try:
                role = Role.objects.get(user=user, institution=institution, name='res')
            except Role.DoesNotExist:
                return Response({'error': 'not allowed to work with institution {0}'.format(kwargs.get('institution'))},
                                status=status.HTTP_401_UNAUTHORIZED)
            login(request, user)
            serializer = SessionRestSerializer(data={
                'sessionid': request.session._session_key,
                'start_date': timezone.now(),
                'expiration_date': timezone.now() + timezone.timedelta(minutes=5),
                'role_id': role.id
            })

            if serializer.is_valid():
                serializer.save()
                return Response({'sessionid': serializer.data.get('sessionid')}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'invalid data'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'error': 'invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'error': 'missing params'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def rest_logout(request, *args, **kwargs):

    if 'HTTP_AUTHORIZATION' in request.META:
        try:
            sessionrest = SessionRest.objects.get(sessionid=request.META.get('HTTP_AUTHORIZATION'))
            sessionrest.delete()
            return Response({'logout': 'ok'}, status=status.HTTP_200_OK)
        except SessionRest.DoesNotExist:
            return Response({'error': 'session not exist'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'error': 'missing headers'}, status=status.HTTP_400_BAD_REQUEST)


def web_logout(request, *args, **kwargs):
    try:
        tokenaccesspatient = TokenAccessPatient.objects.get(token=request.session._session_key)
        tokenaccesspatient.delete()
    except TokenAccessPatient.DoesNotExist:
        pass
    logout(request)
    return HttpResponseRedirect('/html5dicom/login')


def validate_session_expired(sessionrest):
    if sessionrest.expiration_date >= timezone.now():
        sessionrest.expiration_date = timezone.now() + timezone.timedelta(minutes=5)
        sessionrest.save()
        return True
    else:
        SessionStore(session_key=sessionrest.sessionid).delete()
        sessionrest.delete()
        return False


def validate_token_expired(tokenaccesspatient):
    if tokenaccesspatient.expiration_date >= timezone.now():
        tokenaccesspatient.expiration_date = timezone.now() + timezone.timedelta(minutes=5)
        tokenaccesspatient.save()
        return True
    else:
        SessionStore(session_key=tokenaccesspatient.token).delete()
        tokenaccesspatient.delete()
        return False


@api_view(['GET'])
def rest_qido(request, *args, **kwargs):
    if 'HTTP_AUTHORIZATION' in request.META:
        try:
            sessionrest = SessionRest.objects.get(sessionid=request.META.get('HTTP_AUTHORIZATION'))
        except SessionRest.DoesNotExist:
            return Response({'error': 'invalid credentials, session not exist'}, status=status.HTTP_401_UNAUTHORIZED)
        if validate_session_expired(sessionrest):
            full_path = request.get_full_path()
            current_path = full_path[full_path.index('qido/') + 5:]
            url_httpdicom = Setting.objects.get(key='url_httpdicom').value
            url_httpdicom_req = url_httpdicom + '/custodians/titles/' + sessionrest.role.institution.organization.short_name
            url_httpdicom_req += '/aets/' + sessionrest.role.institution.short_name
            oid_inst = requests.get(url_httpdicom_req)
            current_path = url_httpdicom + '/pacs/' + oid_inst.json()[0] + '/rs/' + current_path + sessionrest.role.parameter_rest
            qido_response = requests.get(current_path)
            if qido_response.text != '':
                data_response = qido_response.json()
                for item in data_response:
                    if '00081190' in item:
                        study_data = item['00081190']['Value'][0]
                        try:
                            study_data = study_data[study_data.index('rs') + 3:]
                            wado_url = request.scheme + '://' + request.get_host() + '/proxydcmweb/'
                            wado_url = wado_url + 'wado/' + study_data
                            item['00081190']['Value'] = [wado_url]
                        except Exception as inst:
                            study_data = study_data
                            wado_url = request.scheme + '://' + request.get_host() + '/proxydcmweb/'
                            wado_url = wado_url + 'wado/studies' + study_data
                            item['00081190']['Value'] = [wado_url]
                return Response(data_response, status=status.HTTP_200_OK)
            else:
                return Response({}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'session expired'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'error': 'missing headers'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def rest_wado(request, *args, **kwargs):
    if 'HTTP_AUTHORIZATION' in request.META:
        try:
            sessionrest = SessionRest.objects.get(sessionid=request.META.get('HTTP_AUTHORIZATION'))
        except SessionRest.DoesNotExist:
            return Response({'error': 'invalid credentials, session not exist'}, status=status.HTTP_401_UNAUTHORIZED)
        if validate_session_expired(sessionrest):
            full_path = request.get_full_path()
            current_path = full_path[full_path.index('wado/') + 5:]
            study_data = current_path.split('/')
            if len(study_data) == 2 and study_data[0] == 'studies':
                url_httpdicom = Setting.objects.get(key='url_httpdicom').value
                url_httpdicom_req = url_httpdicom + '/custodians/titles/' + sessionrest.role.institution.organization.short_name
                url_httpdicom_req += '/aets/' + sessionrest.role.institution.short_name
                oid_inst = requests.get(url_httpdicom_req)
                url_zip = url_httpdicom + '/pacs/' + oid_inst.json()[0] + '/dcm.zip?StudyInstanceUID=' + study_data[1]
                wado_response = requests.get(url_zip)
                return HttpResponse(wado_response.content, content_type=wado_response.headers.get('content-type'))
            elif len(study_data) == 4 and study_data[0] == 'studies' and study_data[2] == 'series':
                url_httpdicom = Setting.objects.get(key='url_httpdicom').value
                url_httpdicom_req = url_httpdicom + '/custodians/titles/' + sessionrest.role.institution.organization.short_name
                url_httpdicom_req += '/aets/' + sessionrest.role.institution.short_name
                oid_inst = requests.get(url_httpdicom_req)
                url_zip = url_httpdicom + '/pacs/' + oid_inst.json()[0] + '/dcm.zip?SeriesInstanceUID=' + study_data[3]
                wado_response = requests.get(url_zip)
                return HttpResponse(wado_response.content, content_type=wado_response.headers.get('content-type'))
            else:
                return Response({'error': 'invalid url'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'error': 'session expired'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'error': 'missing headers'}, status=status.HTTP_400_BAD_REQUEST)


def study_web(request, *args, **kwargs):
    if 'token' in kwargs:
        try:
            tokenaccesspatient = TokenAccessPatient.objects.get(token=kwargs.get('token'))
        except TokenAccessPatient.DoesNotExist:
            return HttpResponse({'error': 'invalid credentials, session not exist'}, status=status.HTTP_401_UNAUTHORIZED)
        if validate_token_expired(tokenaccesspatient):
            url_httpdicom = Setting.objects.get(key='url_httpdicom').value
            url_httpdicom_req = url_httpdicom + '/custodians/titles/' + tokenaccesspatient.role.institution.organization.short_name
            oid_org = requests.get(url_httpdicom_req)
            url_httpdicom_req += '/aets/' + tokenaccesspatient.role.institution.short_name
            oid_inst = requests.get(url_httpdicom_req)
            organization = {}
            organization.update({
                "patientID": tokenaccesspatient.patientid,
                "name": tokenaccesspatient.role.institution.organization.short_name,
                "oid": oid_org.json()[0],
                "institution": {
                    'name': tokenaccesspatient.role.institution.short_name,
                    'aet': tokenaccesspatient.role.institution.short_name,
                    'oid': oid_inst.json()[0]
                }
            })
            request.session = SessionStore(session_key=kwargs.get('token'))
            context_user = {'organization': organization, 'httpdicom': request.META['HTTP_HOST']}
            return render(request, template_name='html5dicom/patient_main.html', context=context_user)
        else:
            return HttpResponse({'error': 'session expired'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return HttpResponse({'error': 'missing token'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def token_access_patient(request, *args, **kwargs):
    if 'institution' in request.data and 'user' in request.data and 'password' in request.data and 'patientid' in request.data:
        try:
            institution = Institution.objects.get(short_name=request.data.get('institution'))
        except Institution.DoesNotExist:
            return Response({'error': 'institution does not exist'}, status=status.HTTP_401_UNAUTHORIZED)
        user = authenticate(username=request.data.get('user'), password=request.data.get('password'))
        if user:
            try:
                role = Role.objects.get(user=user, institution=institution, name='res')
            except Role.DoesNotExist:
                return Response({'error': 'not allowed to work with institution {0}'.format(request.data.get('institution'))},
                                status=status.HTTP_401_UNAUTHORIZED)
            login(request, user)
            serializer = TokenAccessPatientSerializer(data={
                'token': request.session._session_key,
                'patientid': request.data.get('patientid'),
                'start_date': timezone.now(),
                'expiration_date': timezone.now() + timezone.timedelta(minutes=5),
                'role_id': role.id
            })

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'invalid data'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'error': 'invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'error': 'missing params'}, status=status.HTTP_400_BAD_REQUEST)