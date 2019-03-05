from django.contrib.auth.decorators import login_required


class LoginRequiredMixin(object):
    '''
    用于给视图类继承
    在视图类父类view调用as_view方法是，加入登录验证login_required
    '''
    @classmethod
    def as_view(cls, **initkwargs):
        # 调用父类的as_view
        view = super(LoginRequiredMixin, cls).as_view(**initkwargs)
        return login_required(view)
