from django.conf.urls import url
from proxyrest import views

urlpatterns = [
    url(r'^rest_login$', views.rest_login, name='login'),
    url(r'^rest_logout$', views.rest_logout, name='rest_logout$'),
    url(r'^logout$', views.web_logout, name='logout'),
    url(r'^qido/', views.rest_qido, name='qido'),
    url(r'^wado/', views.rest_wado, name='wado'),
    url(r'^study_web/(?P<token>[^/]+)', views.study_web, name='study_web'),
    url(r'^patient_login/', views.token_access_patient, name='token_patient'),
]
