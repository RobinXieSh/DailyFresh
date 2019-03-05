from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.core.cache import cache
from django.core.paginator import Paginator
from goods.models import GoodsSKU, GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
from order.models import OrderGoods
from django_redis import get_redis_connection


# 首页视图
class IndexView(View):
    '''首页'''

    def get(self, request):
        '''显示首页'''

        # 尝试获取页面缓存
        context = cache.get('index_page_data')

        if context is None:
            # 获取商品种类信息
            types = GoodsType.objects.all()

            # 获取首页轮播信息
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')

            # 获取首页促销活动信息
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

            # 获取首页分类商品展示信息
            for type in types:
                type.image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
                type.title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

            # 组织模板上下文
            context = {
                'types': types,
                'goods_banners': goods_banners,
                'promotion_banners': promotion_banners,
            }

            # 设置缓存
            cache.set('index_page_data', context, 3600)

        # 获取用户购物车中商品数目
        user = request.user
        if user.is_authenticated():
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)
        else:
            cart_count = 0

        # 模板上下文添加非缓存数据
        context.update(cart_count=cart_count)

        return render(request, 'index.html', context)


# 详情页试图
class DetailView(View):
    '''产品详情页'''

    def get(self, request, goods_id):
        '''显示详情页'''
        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在，返回首页
            return redirect(reverse('goods:index'))

        # 获取商品分类信息
        types = GoodsType.objects.all()

        # 获取评论信息
        order_goods = OrderGoods.objects.filter(sku=sku).exclude(comment='')

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')

        # 获取相同SPU商品
        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)

        # 获取用户购物车中商品数目
        user = request.user
        if user.is_authenticated():
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

            # 添加用户浏览记录
            conn = get_redis_connection('default')
            history_key = 'history_%d' % user.id
            conn.lrem(history_key, 0, sku.id)  # 先移除存在的浏览记录
            conn.lpush(history_key, sku.id)  # 添加浏览记录
            conn.ltrim(history_key, 0, 4)
        else:
            cart_count = 0

        # 组织模板上下文
        context = {
            'sku': sku,
            'types': types,
            'order_goods': order_goods,
            'new_skus': new_skus,
            'same_spu_skus': same_spu_skus,
            'cart_count': cart_count
        }

        return render(request, 'detail.html', context)


# 产品列表页视图
class ListView(View):
    '''产品列表页'''

    def get(self, request, type_id, page_index):
        '''显示列表页'''

        try:
            type = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            # 种类不存
            return redirect(reverse('goods:index'))

        # 获取商品分类信息
        types = GoodsType.objects.all()

        # 获取排序方式
        sort = request.GET.get('sort', 'default')

        # 获取分类商品信息
        if sort == 'price':
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        else:
            sort = 'default'
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        # 分页处理
        paginator = Paginator(skus, 10)

        # 获取分页内容
        try:
            page = int(page_index)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取分页Page对象
        skus_page = paginator.page(page)

        # 页码控制，最多显示5页
        num_pages = paginator.num_pages
        pages = {}
        if num_pages <= 5:
            pages['sign'] = ''
            pages['range'] = range(1, num_pages + 1)
        elif page <= 3:
            pages['sign'] = 'r'
            pages['range'] = range(1, 6)
        elif num_pages - page <= 2:
            pages['sign'] = 'l'
            pages['range'] = range(num_pages - 4, num_pages + 1)
        else:
            pages['sign'] = 'rl'
            pages['range'] = range(page - 2, page + 3)

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=type).order_by('-create_time')

        # 获取用户购物车中商品数目
        user = request.user
        if user.is_authenticated():
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)
        else:
            cart_count = 0

        # 组织模板上下文
        context = {
            'type': type,
            'types': types,
            'skus_page': skus_page,
            'new_skus': new_skus,
            'cart_count': cart_count,
            'pages': pages,
            'sort': sort,
        }

        return render(request, 'list.html', context)

