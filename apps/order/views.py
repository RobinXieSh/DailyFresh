from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.http import JsonResponse
from django.views.generic import View
from django.db import transaction
from django.conf import settings
import os
import time
from datetime import datetime
from alipay import AliPay
from goods.models import GoodsSKU
from user.models import Address
from order.models import OrderInfo, OrderGoods
from django_redis import get_redis_connection


# Create your views here.

class OrderPlaceView(View):
    '''提交订单视图'''

    def post(self, request):
        '''提交订单显示'''
        # 判断是否登录
        user = request.user
        if not user.is_authenticated():
            return redirect(reverse('user:login'))

        # 获取参数
        sku_ids = request.POST.getlist('sku_ids')

        # 校验参数
        if not sku_ids:
            return redirect(reverse('cart:show'))  # 跳转至购物车页面

        # 获取用户购物车缓存
        cart_key = 'cart_%d' % user.id
        conn = get_redis_connection('default')

        skus = []
        total_count = 0
        total_amount = 0
        # 遍历sku_ids获取用户订单商品信息
        for sku_id in sku_ids:
            sku = GoodsSKU.objects.get(id=sku_id)  # 获取商品对象
            count = conn.hget(cart_key, sku_id)  # 获取商品购物车缓存数量
            amount = sku.price * int(count)  # 计算小计
            sku.count = int(count)
            sku.amount = amount
            skus.append(sku)
            total_count += int(count)  # 累计总件数
            total_amount += amount  # 累计总金额

        # 获取用户收货地址
        addrs = Address.objects.filter(user=user)

        # 获取运费
        trans_fee = 10  # 写死
        sku_ids = ','.join(sku_ids)
        # 组织模板上下文
        context = {
            'skus': skus,
            'total_count': total_count,
            'total_amount': total_amount,
            'addrs': addrs,
            'trans_fee': trans_fee,
            'total_pay': total_amount + trans_fee,
            'sku_ids': sku_ids,
        }

        return render(request, 'place_order.html', context)


# 悲观锁解决并发
class OrderCreateView1(View):
    '''订单创建试图'''

    @transaction.atomic
    def post(self, request):
        '''订单创建'''
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')  # 1,3

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHOD.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})

        # todo: 创建订单核心业务

        # 组织参数
        # 订单id: 20171122181630+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()

        try:
            # todo: 向df_order_info表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)

            # todo: 用户的订单中有几个商品，需要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                # 获取商品的信息
                try:
                    # 悲观锁：为df_goods_sku上锁，事务结束，释放锁
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except:
                    transaction.savepoint_rollback(save_id)  # 事务回滚
                    # 商品不存在
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                # 从redis中获取用户所要购买的商品的数量
                count = conn.hget(cart_key, sku_id)

                # 判断商品库存
                if int(count) > sku.skock:
                    transaction.savepoint_rollback(save_id)  # 事务回滚
                    return JsonResponse({'res': 5, 'errmsg': '商品库存不足！'})

                # todo: 向df_order_goods表中添加一条记录
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)

                # todo: 更新商品的库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                # todo: 累加计算订单商品的总数量和总价格
                amount = sku.price * int(count)
                total_count += int(count)
                total_price += amount

            # todo: 更新订单信息表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)  # 事务回滚
            return JsonResponse({'res': 6, 'errmsg': '创建订单失败！'})

        # 事务提交
        transaction.savepoint_commit()

        # todo: 清除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({'res': 7, 'message': '创建成功'})


# 乐观锁解决并发
class OrderCreateView(View):
    '''订单创建试图'''

    @transaction.atomic
    def post(self, request):
        '''订单创建'''
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')  # 1,3

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHOD.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})

        # todo: 创建订单核心业务

        # 组织参数
        # 订单id: 20171122181630+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()

        try:
            # todo: 向df_order_info表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)

            # todo: 用户的订单中有几个商品，需要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                for i in range(3):
                    # 获取商品的信息
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except:
                        transaction.savepoint_rollback(save_id)  # 事务回滚
                        # 商品不存在
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    # 从redis中获取用户所要购买的商品的数量
                    count = conn.hget(cart_key, sku_id)

                    # 判断商品库存
                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(save_id)  # 事务回滚
                        return JsonResponse({'res': 5, 'errmsg': '商品库存不足！'})

                    # todo: 更新商品的库存和销量（使用乐观锁）
                    orgin_stock = sku.stock
                    new_stock = orgin_stock - int(count)
                    new_sales = sku.sales + int(count)
                    # 乐观锁：执行update时重新判断stock与查询时stock是否一致
                    res = GoodsSKU.objects.filter(id=sku_id, stock=orgin_stock).update(stock=new_stock, sales=new_sales)

                    if res == 0:
                        # 尝试3次判断，若3次失败则跳出循环，下单失败！
                        if i == 2:
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 5, 'errmsg': '商品库存不足！'})
                        continue

                    # todo: 向df_order_goods表中添加一条记录
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)

                    # todo: 累加计算订单商品的总数量和总价格
                    amount = sku.price * int(count)
                    total_count += int(count)
                    total_price += amount

                    break

            # todo: 更新订单信息表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            print(e)
            transaction.savepoint_rollback(save_id)  # 事务回滚
            return JsonResponse({'res': 6, 'errmsg': '创建订单失败！'})

        # 事务提交
        transaction.savepoint_commit(save_id)

        # todo: 清除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({'res': 7, 'message': '创建成功'})


# 订单支付
class OrderPayView(View):
    '''订单支付'''

    def post(self, request):
        '''订单支付'''
        # 用户登录判断
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录！'})

        # 判断订单号
        order_id = request.POST.get('order_id')
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单Id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误！'})

        # 支付业务处理
        # 支付宝SDK初始化
        app_private_key_string = open(os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem')).read()
        alipay_public_key_string = open(os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem')).read()
        alipay = AliPay(
            appid="2016092600602823",
            app_notify_url="",  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True,  # 默认False
        )

        # 调用支付接口
        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        total_pay = order.total_price + order.transit_price
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=str(total_pay),
            subject='天天生鲜%s' % order_id,
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 返回应答
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res': 3, 'pay_url': pay_url})


# 查看支付结果
class OrderCheckView(View):
    '''查询支付结果'''

    def post(self, request):
        '''查询支付结果'''
        # 用户登录判断
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录！'})

        # 判断订单号
        order_id = request.POST.get('order_id')
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单Id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误！'})

        # 查询支付业务处理
        # 支付宝SDK初始化
        app_private_key_string = open(os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem')).read()
        alipay_public_key_string = open(os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem')).read()
        alipay = AliPay(
            appid="2016092600602823",
            app_notify_url="",  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True,  # 默认False
        )

        # 调用查询支付结果接口
        while True:
            response = alipay.api_alipay_trade_query(order_id)
            code = response.get('code')
            print(response)
            if code == '10000' or code == '40004':
                trade_status = response.get('trade_status')
                if trade_status == 'TRADE_SUCCESS':
                    # 支付成功
                    trade_no = response.get('trade_no')
                    # 更新订单状态
                    order.trade_no = trade_no
                    order.order_status = 4  # 待评价
                    order.save()
                    return JsonResponse({'res': 4, 'msg': '支付成功！'})
                elif trade_status == 'WAIT_BUYER_PAY':
                    # 等待买家付款
                    time.sleep(5)
                    continue
                else:
                    return JsonResponse({'res': 3, 'errmsg': '支付失败！'})
            else:
                return JsonResponse({'res': 3, 'errmsg': '支付失败！'})
