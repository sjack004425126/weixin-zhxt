class UserInfo:
    """用户信息类，用于存储用户基本信息"""
    def __init__(self):
        self.xs_xh = None  # 学号
        self.dq1_mc = None  # 地区名称
        self.bj_id = None  # 班级ID
        self.sys_pc = None  # 系统批次

    @classmethod
    def from_dict(cls, data):
        """从字典创建对象"""
        user = cls()
        user.xs_xh = data.get('xs_xh')
        user.dq1_mc = data.get('dq1_mc')
        user.bj_id = data.get('bj_id')
        user.sys_pc = data.get('sys_pc')
        return user

    def to_dict(self):
        """转换为字典格式"""
        return {
            'xs_xh': self.xs_xh,
            'dq1_mc': self.dq1_mc,
            'bj_id': self.bj_id,
            'sys_pc': self.sys_pc
        }

    def __getitem__(self, key):
        """支持字典式访问"""
        return getattr(self, key)

    def __setitem__(self, key, value):
        """支持字典式赋值"""
        setattr(self, key, value)

    def get(self, key, default=None):
        """支持get方法"""
        return getattr(self, key, default)