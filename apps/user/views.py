from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.core.paginator import Paginator
# from django.core.mail import send_mail
from django.views.generic import View
from django.conf import settings
from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from user.models import User, Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods
from celery_tasks import tasks
from utils.mixin import LoginRequiredMixin
from django_redis import get_redis_connection

import re


# 注册 /user/register
class RegisterView(View):
    '''注册类'''

    def get(self, request):
        '''返回注册页面'''
        return render(request, 'register.html')

    def post(self, request):
        '''处理用户注册'''
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        c_password = request.POST.get('cpwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 数据完整校验
        if not all([username, password, c_password, email]):
            return render(request, 'register.html', {'errmsg': '注册信息未填写完整！'})

        # 邮箱合法校验
        if not re.match('^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确！'})

        # 两次密码一致性校验
        if password != c_password:
            return render(request, 'register.html', {'errmsg': '两次密码不一致！'})

        # 同意协议校验
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议！'})

        # 用户名重复校验
        try:
            user = User.objects.get(username=username)  # 判断用户是否存在
        except User.DoesNotExist:
            user = None

        if user:
            return render(request, 'register.html', {'errmsg': '该用户名已存在！'})

        # 用户注册
        new_user = User.objects.create_user(username, email, password)
        new_user.is_active = 0  # 设定为未激活
        new_user.save()

        # 发送用户激活邮件
        serializer = Serializer(settings.SECRET_KEY, 3600)  # 使用django秘钥加密绑定，1小时过期
        info = {'confirm': new_user.id}  # 加密信息为User.id
        token = serializer.dumps(info).decode()  # 加密生成token

        # 执行发送邮件
        subject = "天天生鲜欢迎您注册"
        sender = settings.EMAIL_FROM
        receiver = [email]
        mail_href = 'http://192.168.107.129:8000/user/active/%s' % token
        html_msg = '''<h1>%s 欢迎您成为天天生鲜用户</h1>
            请点击下方链接完成激活：</br><a href="%s">%s</a>''' % (username, mail_href, mail_href)
        # send_mail(subject, '', sender, receiver, html_message=html_msg)
        # 使用celery异步执行邮件发送
        tasks.SendMail.delay(subject, '', sender, receiver, html_msg)

        # 跳转首页
        return redirect(reverse('goods:index'))


# 激活 /user/active
class ActiveView(View):
    '''用户激活'''

    def get(self, request, token):
        # 解密token，获取用户id
        serializer = Serializer(settings.SECRET_KEY, 3600)
        try:
            # 激活用户
            info = serializer.loads(token)
            user = User.objects.get(id=info['confirm'])
            user.is_active = 1
            user.save()
        except SignatureExpired:
            return HttpResponse('激活链接已过期')  # 激活链接过期

        return redirect(reverse('user:login'))


# 登录 /user/login
class LoginView(View):
    '''用户登录'''

    def get(self, request):
        '''返回用户登录页面'''
        # 判断是否记录用户名
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''

        return render(request, 'login.html', {'username': username, 'checked': checked})

    def post(self, request):
        '''执行用户登录'''

        # 接收数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')

        # 校验数据
        if not all([username, password]):
            return render(request, 'login.html', {'errmsg': '登录信息未填写完整！'})

        # 登录校验（使用Django内置用户权限系统）
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                # 已激活，记录用户登录状态（django内置user）
                login(request, user)

                # 判断登录后要跳转的地址、默认跳转到首页
                next = request.GET.get('next', reverse('goods:index'))
                response = redirect(next)

                # 判断是否记住用户名
                remember = request.POST.get('remember')
                if remember == 'on':
                    response.set_cookie('username', username, 7 * 24 * 3600)
                else:
                    response.delete_cookie('username')

                return response
            else:
                return render(request, 'login.html', {'errmsg': '用户未激活！'})
        else:
            return render(request, 'login.html', {'errmsg': '用户名或密码错误！'})


# 退出登录 /user/logout
class LogoutView(LoginView):
    '''用户退出'''

    def get(self, request):
        '''执行用户退出'''
        # 清除用户的session信息
        logout(request)
        # 跳转到首页
        return redirect(reverse('goods:index'))


# 用户中心-首页 /user
class UserInfoView(LoginRequiredMixin, View):
    '''用户中心-首页'''

    def get(self, request):
        # 获取用户基本信息
        user = request.user
        address = Address.objects.get_default_address(user)  # 获取用户默认地址

        # 获取用户浏览记录
        conn = get_redis_connection('default')
        history_key = 'history_%d' % user.id
        sku_ids = conn.lrange(history_key, 0, 4)  # 获取前5个浏览记录

        # 从db中获取浏览记录商品信息
        history_goods_skus = []
        for sku_id in sku_ids:
            history_goods_skus.append(GoodsSKU.objects.get(id=sku_id))

        # 组织上下文
        context = {
            'page': 'info',
            'address': address,
            'history_goods_skus': history_goods_skus
        }

        return render(request, 'user_center_info.html', context)


# 用户中心-订单 /user/order
class UserOrderView(LoginRequiredMixin, View):
    '''用户中心-订单'''

    def get(self, request, page):
        "显示用户订单"
        # 获取用户订单信息
        user = request.user
        if not user.is_authenticated():
            return redirect(reverse('user:login'))

        # 获取用户订单信息
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')

        # 遍历订单获取订单商品信息
        for order in orders:
            order_goods = OrderGoods.objects.filter(order=order)

            # 遍历计算商品小计
            for order_good in order_goods:
                amount = order_good.count * order_good.price
                order_good.amount = amount

            order.order_goods = order_goods

            # 处理订单状态
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

            # 处理支付类型
            order.pay_method_name = OrderInfo.PAY_METHOD[str(order.pay_method)]

            # 处理总金额
            order.total_amount = order.total_price + order.transit_price

        # 分页处理
        paginator = Paginator(orders, 3)

        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        order_page = paginator.page(page)

        # 页码控制，最多显示5页
        num_pages = paginator.num_pages
        if num_pages <= 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        # 组织模板上下文
        context = {
            'page': 'order',
            'order_page': order_page,
            'pages': pages,
        }

        return render(request, 'user_center_order.html', context)


# 用户中心-地址 /user/address
class AddressView(LoginRequiredMixin, View):
    '''用户中心-地址'''

    def get(self, request):
        '''显示页面'''
        # 获取用户默认地址信息
        user = request.user
        address = Address.objects.get_default_address(user)

        return render(request, 'user_center_site.html', {'page': 'address', 'address': address})

    def post(self, request):
        '''提交地址信息'''
        # 接受数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 校验数据
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg': '信息不完整！'})

        # 校验手机
        if not re.match(r'^1[34578]\d{9}$', phone):
            return render(request, 'user_center_site.html', {'errmsg': '手机格式不正确！'})

        # 业务处理：添加地址
        # 判断是否已有默认地址，无则添加地址未默认地址
        user = request.user
        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回应答
        return redirect(reverse('user:address'))  # get请求方式访问
