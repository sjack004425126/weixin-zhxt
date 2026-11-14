const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    // 报考状态
    registrationOpen: false,
    reexamDeadline: '',
    // 课程分类
    failedCourses: [],    // 不及格/可报考
    passedCourses: [],    // 已通过
    repairCourses: [],         // 补修课（全部，用于索引查找）
    repairFailedCourses: [],   // 补修课-未通过
    repairPassedCourses: [],   // 补修课-已通过
    // 统计
    totalCount: 0,
    failedCount: 0,
    passedCount: 0,
    registeredCount: 0,
    needPayCount: 0,
    repairCount: 0,
    // UI状态
    showPassed: false,
    isLoading: true,
    // 选中的课程（用于批量报考）
    selectedIds: {},
  },

  onLoad() {},

  onShow() {
    this.loadData();
  },

  async loadData() {
    this.setData({ isLoading: true });
    try {
      const res = await tokenGet('/bkbk/list', {}, { loadingTitle: '加载中...' });
      const d = res;
      const planList = d.plan_list || [];

      // 分类
      const failed = [];
      const passed = [];
      planList.forEach(item => {
        if (item.is_pass) {
          passed.push(item);
        } else {
          failed.push(item);
        }
      });

      // 统计已报考数（含补修课）
      const repairList = d.repair_plan || [];
      const repairFailed = [];
      const repairPassed = [];
      repairList.forEach(item => {
        if (item.is_pass) {
          repairPassed.push(item);
        } else {
          repairFailed.push(item);
        }
      });
      const registeredCount = failed.filter(c => c.register_status === '已报考').length
        + repairList.filter(c => c.register_status === '已报考').length;
      // 需要缴费的课程数（已报考且未支付，排除补修课因为补修课免费）
      const needPayCount = failed.filter(c => c.register_status === '已报考' && c.pay_status !== '已支付').length;

      this.setData({
        registrationOpen: d.registration_open,
        reexamDeadline: d.reexam_deadline || '',
        failedCourses: failed,
        passedCourses: passed,
        repairCourses: repairList,
        repairFailedCourses: repairFailed,
        repairPassedCourses: repairPassed,
        totalCount: planList.length,
        failedCount: failed.length,
        passedCount: passed.length,
        registeredCount,
        needPayCount,
        repairCount: repairList.length,
        isLoading: false,
      });
    } catch (err) {
      this.setData({ isLoading: false });
      this.showError(err.message || '获取数据失败');
    }
  },

  // 切换已通过课程显示
  togglePassed() {
    this.setData({ showPassed: !this.data.showPassed });
  },

  // 在 failedCourses 中找到指定 kcid 的索引
  _findFailedIndex(kcid) {
    return this.data.failedCourses.findIndex(c => c.kcid === kcid);
  },

  // 在 repairCourses 中找到指定 kcid 的索引
  _findRepairIndex(kcid) {
    return this.data.repairCourses.findIndex(c => c.kcid === kcid);
  },

  // 在 repairFailedCourses 中找到指定 kcid 的索引
  _findRepairFailedIndex(kcid) {
    return this.data.repairFailedCourses.findIndex(c => c.kcid === kcid);
  },

  // 报考（普通课程）
  async handleRegister(e) {
    const course = e.currentTarget.dataset.course;
    if (!this.data.registrationOpen) {
      this.showError('补考报名已关闭');
      return;
    }
    try {
      await tokenPost('/bkbk/register', {
        course_id: course.kcid,
        course_name: course.kcmc,
        college_name: course.ksdw
      });
      const idx = this._findFailedIndex(course.kcid);
      if (idx !== -1) {
        this.setData({
          [`failedCourses[${idx}].register_status`]: '已报考',
          [`failedCourses[${idx}].can_register`]: false,
          [`failedCourses[${idx}].pay_status`]: '未支付',
          registeredCount: this.data.registeredCount + 1,
          needPayCount: this.data.needPayCount + 1
        });
      }
      this.showSuccess('报考成功');
    } catch (err) {
      this.showError(err.message || '报考失败');
    }
  },

  // 取消报考（普通课程）
  async handleCancel(e) {
    const course = e.currentTarget.dataset.course;
    if (!this.data.registrationOpen) {
      this.showError('补考报名已关闭');
      return;
    }
    if (course.pay_status === '已支付') {
      this.showError('已支付课程不能取消');
      return;
    }
    try {
      await tokenPost('/bkbk/cancel', {
        course_id: course.kcid
      });
      const idx = this._findFailedIndex(course.kcid);
      if (idx !== -1) {
        this.setData({
          [`failedCourses[${idx}].register_status`]: '未报考',
          [`failedCourses[${idx}].can_register`]: true,
          [`failedCourses[${idx}].pay_status`]: '-',
          registeredCount: this.data.registeredCount - 1,
          needPayCount: this.data.needPayCount - 1
        });
      }
      this.showSuccess('取消成功');
    } catch (err) {
      this.showError(err.message || '取消失败');
    }
  },

  // 报考（补修课）
  async handleRepairRegister(e) {
    const course = e.currentTarget.dataset.course;
    if (!this.data.registrationOpen) {
      this.showError('补考报名已关闭');
      return;
    }
    try {
      await tokenPost('/bkbk/register', {
        course_id: course.kcid,
        course_name: course.kcmc,
        college_name: '分部'
      });
      // 补修课报考后后端直接设为已支付（免费）
      const idx = this._findRepairFailedIndex(course.kcid);
      if (idx !== -1) {
        this.setData({
          [`repairFailedCourses[${idx}].register_status`]: '已报考',
          [`repairFailedCourses[${idx}].can_register`]: false,
          [`repairFailedCourses[${idx}].pay_status`]: '已支付',
          registeredCount: this.data.registeredCount + 1
        });
      }
      this.showSuccess('报考成功（补修课免费）');
    } catch (err) {
      this.showError(err.message || '报考失败');
    }
  },

  // 取消报考（补修课）
  async handleRepairCancel(e) {
    const course = e.currentTarget.dataset.course;
    if (!this.data.registrationOpen) {
      this.showError('补考报名已关闭');
      return;
    }
    if (course.pay_status === '已支付') {
      this.showError('已支付课程不能取消');
      return;
    }
    try {
      await tokenPost('/bkbk/cancel', {
        course_id: course.kcid
      });
      const idx = this._findRepairFailedIndex(course.kcid);
      if (idx !== -1) {
        this.setData({
          [`repairFailedCourses[${idx}].register_status`]: '未报考',
          [`repairFailedCourses[${idx}].can_register`]: true,
          [`repairFailedCourses[${idx}].pay_status`]: '-',
          registeredCount: this.data.registeredCount - 1
        });
      }
      this.showSuccess('取消成功');
    } catch (err) {
      this.showError(err.message || '取消失败');
    }
  },

  // 去缴费
  async goToPayment() {
    if (this.data.needPayCount <= 0) {
      this.showError('没有需要支付的课程');
      return;
    }

    // 检查是否有需要付费的课程（排除补修课已支付的）
    const needPay = this.data.failedCourses.filter(
      c => c.register_status === '已报考' && c.pay_status !== '已支付'
    );
    if (needPay.length === 0) {
      this.showError('所有已报考课程均已支付');
      return;
    }

    try {
      // 获取微信登录code
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({
          success: resolve,
          fail: () => reject('微信登录失败，请重试')
        });
      });

      const res = await tokenPost('/bkbk/pay', {
        code: loginRes.code
      });

      // 拉起微信支付
      const payParams = res.pay_params;
      await new Promise((resolve, reject) => {
        wx.requestPayment({
          timeStamp: payParams.timeStamp,
          nonceStr: payParams.nonceStr,
          package: payParams.package,
          signType: payParams.signType || 'RSA',
          paySign: payParams.paySign,
          success: resolve,
          fail: (err) => {
            if (err.errMsg && err.errMsg.includes('cancel')) {
              reject('支付已取消');
            } else {
              reject('支付失败，请重试');
            }
          }
        });
      });

      this.showSuccess('支付成功');
      // 支付成功后刷新数据
      this.loadData();
    } catch (err) {
      this.showError(err.message || '支付失败');
    }
  },

  goHome() {
    wx.switchTab({ url: '/pages/home/home' });
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh());
  },
}, {
  requireAuth: true
});
