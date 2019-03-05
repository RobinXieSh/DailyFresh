import django
import os
from django.core.mail import send_mail
from django.template import loader, RequestContext
from django.conf import settings
# from celery import Celery
from celery import task
from goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner


# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh.settings")
# django.setup()
# app = Celery('celery_tasks.tasks', broker='redis://192.168.107.129:6379/5')


# @app.task
@task
def SendMail(subject, message, sender, receiver, html_message):
    '''发送邮件'''
    send_mail(subject, message, sender, receiver, html_message=html_message)


@task
def generate_static_index_html():
    '''产生首页静态页面'''

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
        'cart_count': '0'
    }

    # 加载模板文件
    temp = loader.get_template('static_index.html')
    # 模板渲染
    static_index_html = temp.render(context)

    print(1)
    # 生成首页对应静态文件
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(static_index_html)
