from django.contrib import admin
from django.core.cache import cache
from goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, GoodsSKU, IndexTypeGoodsBanner
from celery_tasks.tasks import generate_static_index_html


class BaseModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        '''新增或更新数据时调用'''
        super().save_model(request, obj, form, change)

        # 发出任务，让celery worker重新生成静态页面
        generate_static_index_html.delay()

        # 清除view页面缓存
        cache.delete('index_page_data')

    def delete_model(self, request, obj):
        '''删除数据时调用'''
        super().delete_model(request, obj)

        # 发出任务，让celery worker重新生成静态页面
        generate_static_index_html.delay()

        # 清除view页面缓存
        cache.delete('index_page_data')


class GoodsTypeAdime(BaseModelAdmin):
    pass


class IndexGoodsBannerAdime(BaseModelAdmin):
    pass


class IndexPromotionBannerAdime(BaseModelAdmin):
    pass


class GoodsSKUAdime(BaseModelAdmin):
    pass


class IndexTypeGoodsBannerAdime(BaseModelAdmin):
    pass


admin.site.register(GoodsType, GoodsTypeAdime)
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdime)
admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdime)
admin.site.register(GoodsSKU, GoodsSKUAdime)
admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBannerAdime)
