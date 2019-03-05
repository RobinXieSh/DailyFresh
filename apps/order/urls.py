from django.conf.urls import url
from order.views import OrderPlaceView, OrderCreateView, OrderPayView, OrderCheckView

urlpatterns = [
    url(r'^place$', OrderPlaceView.as_view(), name='place'),
    url(r'^create$', OrderCreateView.as_view(), name='create'),
    url(r'^pay$', OrderPayView.as_view(), name='pay'),
    url(r'^check$', OrderCheckView.as_view(), name='check'),
]
