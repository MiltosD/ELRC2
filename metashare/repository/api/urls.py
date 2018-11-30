from django.conf.urls import patterns, url

urlpatterns = patterns(
    'metashare.repository.api.views',
    url(r'get_data/(?P<object_id>\w+)/$', 'get_data', name='get_data'),
    url(r'upload_data/(?P<object_id>\w+)/$', 'upload_data', name='upload_data'),
    url(r'get_xml/(?P<object_id>\w+)/$', 'get_xml', name='upload_data')
)
