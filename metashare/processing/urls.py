from django.conf.urls import patterns, url

urlpatterns = patterns('metashare.processing.views',
                       url(r'^$', 'services'),
                       url(r'^process/(?P<resource_id>\w+)/$', 'process_repo_resource'),
                       url(r'^data-transaction/$', 'get_data'),
                       url(r'^download/(?P<processing_id>\w+)/$', 'download_processed_data')
                       )
