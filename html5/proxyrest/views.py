from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.core.urlresolvers import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
import requests
import uuid
from proxyrest.models import SessionRest, TokenAccessPatient, TokenAccessStudy
from html5dicom.models import Institution, Role, Setting, UserViewerSettings
from html5dicom.views import weasis, osirix, cornerstone
from proxyrest.serializers import TokenAccessPatientSerializer, SessionRestSerializer, TokenAccessStudySerializer
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


def validate_token_expired(token_access):
    if token_access.expiration_date >= timezone.now():
        return True
    else:
        token_access.delete()
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
            token_access = TokenAccessPatient.objects.get(token=kwargs.get('token'))
            type_token = 'patient'
        except TokenAccessPatient.DoesNotExist:
            try:
                token_access = TokenAccessStudy.objects.get(token=kwargs.get('token'))
                type_token = 'study'
            except TokenAccessStudy.DoesNotExist:
                return JsonResponse({'error': 'invalid credentials, session not exist'}, status=status.HTTP_401_UNAUTHORIZED)
        if validate_token_expired(token_access):
            try:
                config_toolbar = Setting.objects.get(key='toolbar_patient').value
            except Setting.DoesNotExist:
                config_toolbar = 'full'
            if token_access.viewerType != '':
                user_viewer = token_access.viewerType
            else:
                try:
                    user_viewer = UserViewerSettings.objects.get(user=token_access.role.user).viewer
                except UserViewerSettings.DoesNotExist:
                    user_viewer = ''
            url_httpdicom = Setting.objects.get(key='url_httpdicom').value
            url_httpdicom_req = url_httpdicom + '/custodians/titles/' + token_access.role.institution.organization.short_name
            oid_org = requests.get(url_httpdicom_req)
            url_httpdicom_req += '/aets/' + token_access.role.institution.short_name
            oid_inst = requests.get(url_httpdicom_req)
            login(request, token_access.role.user)
            organization = {}
            if (type_token == 'patient') or (type_token == 'study' and token_access.viewerType == ''):
                if type_token == 'patient':
                    organization.update({
                        "patientID": token_access.PatientID,
                        "seriesSelection": token_access.seriesSelection,
                        "StudyInstanceUID": "",
                        "name": token_access.role.institution.organization.short_name,
                        "oid": oid_org.json()[0],
                        "config_toolbar": config_toolbar,
                        "institution": {
                            'name': token_access.role.institution.short_name,
                            'aet': token_access.role.institution.short_name,
                            'oid': oid_inst.json()[0]
                        }
                    })
                elif type_token == 'study' and token_access.viewerType == '':
                    organization.update({
                        "patientID": "",
                        "seriesSelection": "",
                        "StudyInstanceUID": token_access.StudyInstanceUID,
                        "name": token_access.role.institution.organization.short_name,
                        "oid": oid_org.json()[0],
                        "config_toolbar": config_toolbar,
                        "institution": {
                            'name': token_access.role.institution.short_name,
                            'aet': token_access.role.institution.short_name,
                            'oid': oid_inst.json()[0]
                        }
                    })
                context_user = {'organization': organization, 'httpdicom': request.META['HTTP_HOST'],
                                'user_viewer': user_viewer, 'navbar': 'rest'}
                return render(request, template_name='html5dicom/patient_main.html', context=context_user)
            elif type_token == 'study' and token_access.viewerType != '':
                if token_access.viewerType == 'cornerstone':
                    request.GET._mutable = True
                    request.GET.__setitem__('requestType', 'STUDY')
                    request.GET.__setitem__('study_uid', token_access.StudyInstanceUID)
                    request.GET.__setitem__('custodianOID', oid_inst.json()[0])
                    request.GET._mutable = False
                    json_cornerstone = cornerstone(request)
                    return render(request, template_name='html5dicom/redirect_cornerstone.html', context={'json_cornerstone': json_cornerstone.content})
                elif token_access.viewerType == 'weasis':
                    request.GET._mutable = True
                    request.GET.__setitem__('requestType', 'STUDY')
                    request.GET.__setitem__('study_uid', token_access.StudyInstanceUID)
                    request.GET.__setitem__('custodianOID', oid_inst.json()[0])
                    request.GET._mutable = False
                    return weasis(request)
                elif token_access.viewerType == 'zip':
                    request.GET._mutable = True
                    request.GET.__setitem__('session', request.session._session_key)
                    request.GET.__setitem__('requestType', 'STUDY')
                    request.GET.__setitem__('study_uid', token_access.StudyInstanceUID)
                    request.GET.__setitem__('custodianOID', oid_inst.json()[0])
                    request.GET._mutable = False
                    return osirix(request)
                elif token_access.viewerType == 'osirix':
                    response = HttpResponse("", status=302)
                    response['Location'] = "osirix://?methodName=DownloadURL&Display=YES&URL='" + request.build_absolute_uri(reverse('osirix')) + "?requestType=STUDY&study_uid=" + token_access.StudyInstanceUID + "&session=" + request.session._session_key + "&custodianOID=" + oid_inst.json()[0] + "'"
                    return response
        else:
            return JsonResponse({'error': 'session expired'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return HttpResponse({'error': 'missing token'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def token_access_patient(request, *args, **kwargs):
    if 'institution' in request.data and 'user' in request.data and 'password' in request.data and 'PatientID' in request.data:
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
            try:
                allowed_age = int(Setting.objects.get(key='allowed_age_token_patient').value)
            except Setting.DoesNotExist:
                allowed_age = 120
            serializer = TokenAccessPatientSerializer(data={
                'token': request.session._session_key,
                'PatientID': request.data.get('PatientID'),
                'IssuerOfPatientID': request.data.get('IssuerOfPatientID', ''),
                'IssuerOfPatientIDQualifiers': request.data.get('IssuerOfPatientIDQualifiers', ''),
                'StudyDate': request.data.get('StudyDate', ''),
                'viewerType': request.data.get('viewerType', ''),
                'seriesSelection': request.data.get('seriesSelection', ''),
                'start_date': timezone.now(),
                'expiration_date': timezone.now() + timezone.timedelta(seconds=allowed_age),
                'role_id': role.id
            })

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'invalid data', 'description': serializer.errors}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'error': 'invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'error': 'missing params'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def token_access_study(request, *args, **kwargs):
    if 'institution' in request.data and 'user' in request.data and 'password' in request.data and 'StudyInstanceUID' in request.data:
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
            try:
                allowed_age = int(Setting.objects.get(key='allowed_age_token_study').value)
            except Setting.DoesNotExist:
                allowed_age = 120
            serializer = TokenAccessStudySerializer(data={
                'token': request.session._session_key,
                'StudyInstanceUID': request.data.get('StudyInstanceUID'),
                'viewerType': request.data.get('viewerType', ''),
                'start_date': timezone.now(),
                'expiration_date': timezone.now() + timezone.timedelta(seconds=allowed_age),
                'role_id': role.id
            })

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'invalid data', 'description': serializer.errors}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'error': 'invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'error': 'missing params'}, status=status.HTTP_400_BAD_REQUEST)
