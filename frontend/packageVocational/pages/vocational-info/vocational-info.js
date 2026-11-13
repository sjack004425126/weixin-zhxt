const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');

// ============================================================
// 字典（前端硬编码，与 vocational-info-verify 保持一致）
// ============================================================

// 居住地类型 jzdlx
const JZDLX_MAP = {
  '1': '农村',
  '2': '县城',
  '3': '乡镇非农',
  '4': '城市'
};

// 监护人关系 jzgx
const JZGX_MAP = {
  '1': '父亲',
  '2': '母亲',
  '3': '继父或养父',
  '4': '继母或养母',
  '5': '祖父',
  '6': '祖母',
  '7': '外祖父',
  '8': '外祖母',
  '9': '兄',
  '10': '姐姐',
  '11': '其他亲属',
  '12': '非亲属'
};

// 政治面貌 zzmm
const ZZMM_MAP = {
  '1': '中国共产主义青年团团员',
  '2': '群众',
  '3': '中国共产党党员',
  '4': '中国共产党预备党员'
};

// 户口性质 hkxz（暂用常用值，未知显示原值）
const HKXZ_MAP = {
  '1': '农业户口',
  '2': '非农业户口'
};

// 民族 mz
const MZ_MAP = {
  '01': '汉族',
  '02': '蒙古族',
  '03': '回族',
  '04': '藏族',
  '05': '维吾尔族',
  '06': '苗族',
  '07': '彝族',
  '08': '壮族',
  '09': '布依族',
  '10': '朝鲜族',
  '11': '满族',
  '12': '侗族',
  '13': '瑶族',
  '14': '白族',
  '15': '土家族',
  '16': '哈尼族',
  '17': '哈萨克族',
  '18': '傣族',
  '19': '黎族',
  '20': '傈僳族',
  '21': '佤族',
  '22': '畲族',
  '23': '高山族',
  '24': '拉祜族',
  '25': '水族',
  '26': '东乡族',
  '27': '纳西族',
  '28': '景颇族',
  '29': '柯尔克孜族',
  '30': '土族',
  '31': '达斡尔族',
  '32': '仫佬族',
  '33': '羌族',
  '34': '布朗族',
  '35': '撒拉族',
  '36': '毛南族',
  '37': '仡佬族',
  '38': '锡伯族',
  '39': '阿昌族',
  '40': '普米族',
  '41': '塔吉克族',
  '42': '怒族',
  '43': '乌孜别克族',
  '44': '俄罗斯族',
  '45': '鄂温克族',
  '46': '德昂族',
  '47': '保安族',
  '48': '裕固族',
  '49': '京族',
  '50': '塔塔尔族',
  '51': '独龙族',
  '52': '鄂伦春族',
  '53': '赫哲族',
  '54': '门巴族',
  '55': '珞巴族',
  '56': '基诺族'
};

const FIELD_DICT = {
  jzdlx: JZDLX_MAP,
  jzgx: JZGX_MAP,
  zzmm: ZZMM_MAP,
  hkxz: HKXZ_MAP,
  mz: MZ_MAP
};

// 把数字字符串或值翻译成中文；找不到则原样返回
function resolveText(field, rawValue) {
  if (rawValue === undefined || rawValue === null) return '';
  const map = FIELD_DICT[field];
  const strVal = String(rawValue).trim();
  if (!strVal) return '';
  if (map && map[strVal] !== undefined) return map[strVal];
  return strVal;
}

// ============================================================

createPage({
  data: {
    studentInfo: null,
    loading: true,
    errorMsg: ''
  },

  onLoad() {
    this.loadStudentInfo()
  },

  onShow() {
    if (!this.data.loading) {
      this.loadStudentInfo()
    }
  },

  onPullDownRefresh() {
    this.loadStudentInfo().finally(() => {
      wx.stopPullDownRefresh()
    })
  },

  async loadStudentInfo() {
    try {
      this.setData({
        loading: true,
        errorMsg: ''
      })

      const response = await tokenGet('/vocational_info/get_student_info')

      if (response && response.student) {
        const studentInfo = {
          ...response.student,
          ...(response.ex_info || {})
        }

        studentInfo.xjztText = this.getStatusText(studentInfo.xjzt)
        studentInfo.xjztIcon = this.getStatusIcon(studentInfo.xjzt)

        // 把数字字段翻译成中文
        studentInfo.jzdlxText = resolveText('jzdlx', studentInfo.jzdlx)
        studentInfo.jzgxText = resolveText('jzgx', studentInfo.jzgx)
        studentInfo.zzmmText = resolveText('zzmm', studentInfo.zzmm)
        studentInfo.hkxzText = resolveText('hkxz', studentInfo.hkxz)
        studentInfo.mzText = resolveText('mz', studentInfo.mz)

        this.setData({
          studentInfo: studentInfo,
          loading: false
        })
      } else {
        throw new Error('获取学生信息失败')
      }
    } catch (error) {
      console.error('加载学生信息失败:', error)
      this.setData({
        loading: false,
        errorMsg: error.message || '加载失败，请重试'
      })
      this.showError('获取学生信息失败')
    }
  },

  retry() {
    this.loadStudentInfo()
  },

  showError(message) {
    if (this.selectComponent && this.selectComponent('#top-message')) {
      const topMessage = this.selectComponent('#top-message')
      if (typeof topMessage.showError === 'function') {
        topMessage.showError(message)
      } else {
        wx.showToast({ title: message, icon: 'none', duration: 2000 })
      }
    } else {
      wx.showToast({ title: message, icon: 'none', duration: 2000 })
    }
  },

  showSuccess(message) {
    if (this.selectComponent && this.selectComponent('#top-message')) {
      const topMessage = this.selectComponent('#top-message')
      if (typeof topMessage.showSuccess === 'function') {
        topMessage.showSuccess(message)
      } else {
        wx.showToast({ title: message, icon: 'success', duration: 2000 })
      }
    } else {
      wx.showToast({ title: message, icon: 'success', duration: 2000 })
    }
  },

  getStatusText(status) {
    const statusMap = {
      1: '在籍',
      0: '未在籍'
    }
    return statusMap[status] || '未知'
  },

  getStatusIcon(status) {
    const iconMap = {
      1: 'passed',
      0: 'close'
    }
    return iconMap[status] || 'info-o'
  },

  onShareAppMessage() {
    return {
      title: '学生信息查看',
      path: '/pages/vocational-info/vocational-info'
    }
  },

  onShareTimeline() {
    return {
      title: '学生信息查看'
    }
  },

  goToInfoVerify() {
    wx.navigateTo({
      url: '/packageVocational/pages/vocational-info-verify/vocational-info-verify'
    });
  }
}, {
  requireAuth: true,
  userType: 'vocational_student'
})
