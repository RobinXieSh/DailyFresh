from django.conf.urls import url
# from django.contrib.auth.decorators import login_required
from user.views import RegisterView, ActiveView, LoginView, LogoutView, UserInfoView, UserOrderView, AddressView

urlpatterns = [
    url(r'^register$', RegisterView.as_view(), name='register'),  # /user/register 用户注册
    url(r'^active/(?P<token>.*)$', ActiveView.as_view(), name='active'),  # /user/active 用户激活
    url(r'^login$', LoginView.as_view(), name='login'),  # /user/login 用户登录
    url(r'^logout$', LogoutView.as_view(), name='logout'),  # /user/logout 用户退出
    url(r'^$', UserInfoView.as_view(), name='user'),  # /user 用户中心-首页
    url(r'^order/(?P<page>\d+)$', UserOrderView.as_view(), name='order'),  # /user/order 用户中心-首页
    url(r'^address$', AddressView.as_view(), name='address'),  # /user/address 用户中心-首页
]
