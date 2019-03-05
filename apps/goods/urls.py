from django.conf.urls import url
from goods.views import IndexView, DetailView, ListView

urlpatterns = [
    url(r'^$', IndexView.as_view(), name='index'),
    url(r'^detail/(?P<goods_id>\d+)$', DetailView.as_view(), name='detail'),
    url(r'^list/(?P<type_id>\d)/(?P<page_index>\d)$', ListView.as_view(), name='list'),
]
