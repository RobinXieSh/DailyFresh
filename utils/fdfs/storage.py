from django.core.files.storage import Storage
from django.conf import settings
from fdfs_client.client import Fdfs_client


class FDFSStorage(Storage):
    '''FastDFS文件存储类'''

    def __init__(self, client_conf=None, base_url=None):
        '''初始化'''
        if client_conf is None:
            client_conf = settings.FDFS_CLIENT_CONF
        self.client_conf = client_conf

        if base_url is None:
            base_url = settings.FDFS_BASE_URL
        self.base_url = base_url

    def _open(self, name, mode='rb'):
        '''打开文件'''
        # 由于使用fdfs不需要从服务器打开文件，
        # 而是远程使用ngnix访问文件，所以不需要处理
        pass

    def _save(self, name, content):
        '''保存文件'''

        # 创建Fdfs_Client对象
        client = Fdfs_client(self.client_conf)

        # 上传文件到FastDFS服务器中
        res = client.upload_by_buffer(content.read())

        # dict
        # {
        #     'Group name': group_name,
        #     'Remote file_id': remote_file_id,
        #     'Status': 'Upload successed.',
        #     'Local file name': '',
        #     'Uploaded size': upload_size,
        #     'Storage IP': storage_ip
        # }

        if res.get('Status') != 'Upload successed.':
            raise Exception('上传文件至FastDFS服务器失败！')

        filename = res.get('Remote file_id')

        return filename

    def exists(self, name):
        '''判断是否存在'''
        # 由于文件保存在远程服务器fdfs，所以不需要判断，永远可用
        return False

    def url(self, name):
        '''返回访问文件的url路径'''
        return self.base_url + name
