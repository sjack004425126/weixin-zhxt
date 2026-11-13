const { createPage } = require('../../utils/page-mixin');
const { get } = require('../../utils/request');
const icons = require('../../utils/icons.js');
const { evaluateWindow } = require('../../utils/category-window');
const { STATIC_IMAGES } = require('../../utils/static-images');

// 功能开关检查配置：code 对应数据库 lw_feature_switch.code
const FEATURE_CODES = {
  goToNewZZStudentSignUp:    'zzbm',       // 中职新生报名
  goToNewZZStudentPayment:   'zzpay',      // 中职新生缴费
  goToNewStudentSignUp:      'kfbm',       // 开放新生报名
  goToNewStudentPayment:     'kfpay',      // 开放新生缴费
  goToThreePlusFourRegister: '34',         // 3+4报名
  goToGraduateEmploymentSurvey: 'graduate',  // 毕业生就业调查
  goToAdultExamEnroll:      'adult',       // 成人教育预报名
  goToFeedback:             'feedback',     // 维修及建议
  goToAdminNav:             'admin',       // 管理中心
  handleRegisterBtnTap:      'job',         // 就业推荐
  goToExameMini:            'exame',        // 在线考试小程序
  goToMeterRecharge:        'dianbiao',     // 电表充值（输入电表名 → 二维码）
};

createPage({

  /**
   * 页面的初始数据
   */
  data: {
    notices: [
      { id: 1, title: '2026年秋季承认招生已开始，点击查看' }
    ],
    icons,
    images: {
      banner: STATIC_IMAGES.homeBg,
      logo: STATIC_IMAGES.logo,
      videoCover: STATIC_IMAGES.videoCover,
      // 首页四个功能入口图标
      zbm: STATIC_IMAGES.zbm,
      zsf: STATIC_IMAGES.zsf,
      kbm: STATIC_IMAGES.kbm,
      ksf: STATIC_IMAGES.ksf
    },
    // 数据统计动画
    animatedYear: 0,
    animatedStudents: 0,
    animatedTotal: 0,
    navItems: [
      { type: 'intro', text: '学校简介' },
      { type: 'enroll', text: '招生简章' },
      { type: 'promotion_qr', text: '中职迎新', highlighted: true },
      { type: 'qa', text: '常见问题' }
    ],
    showVideo: false,
    feedId: 'export/UzFfAgtgekIEAQAAAAAAs80X1t2a0gAAAAstQy6ubaLX4KHWvLEZgBPE9aEgBTZ2ZbOJzNPgMJp7E8GoXUAOU9IM_Dfh5HY_', // 视频ID
    finderUserName: 'sphZ7xkhVEBm6IP', // 视频号ID
    showSignUpImage: false, // 控制图片展示
    signUpImageUrl: STATIC_IMAGES.gkbm001,
    registerBtnX: 0,
    registerBtnY: 0,
    screenWidth: 0,
    screenHeight: 0,
    // 重要通知：用户可关闭（一天内不再显示）
    showImportantNotice: true,
    importantNoticeDate: '',
    // 功能开关缓存（key=code，value={is_enabled, tip_message, ts}）
    // 每次 onShow 时清空，强制重新请求后端，保证管理员改了数据库用户能立刻感知
    _featureSwitches: {},
    _featureSwitchesTS: {},
    // 开关"版本号"——后端写入新值后前端只要拿到新版本号就清缓存
    _featureSwitchesVersion: 0
  },

  /**
   * 统一开关检查 + 跳转
   * @param {string} code - lw_feature_switch.code
   * @param {string} targetUrl - 要跳转的页面路径
   * @param {Function} [beforeNavigate] - 跳转前的额外处理（可选），返回 true 才跳转
   */
  async _checkSwitchAndNavigate(code, targetUrl, beforeNavigate) {
    console.log('[home._checkSwitchAndNavigate] code=', code, 'targetUrl=', targetUrl);
    // 缓存只活 5 秒。5 秒内的重复点击复用缓存，但管理员改 DB 后最多等 5 秒即可生效
    const TTL_MS = 5000
    const now = Date.now()
    const cached = this.data._featureSwitches[code]
    const ts = this.data._featureSwitchesTS[code] || 0
    if (!cached || now - ts > TTL_MS) {
      try {
        const res = await get('/feature_switch/check/' + code, {}, { showLoading: false });
        console.log('[home._checkSwitchAndNavigate] switch response:', res);
        const data = (typeof res === 'object' && res !== null)
          ? res
          : { is_enabled: res === true, tip_message: '' };
        // ⚠️ 微信小程序 setData 不支持深路径，必须用展开运算符合并对象
        const sw = Object.assign({}, this.data._featureSwitches, { [code]: data });
        const ts2 = Object.assign({}, this.data._featureSwitchesTS, { [code]: now });
        this.setData({ _featureSwitches: sw, _featureSwitchesTS: ts2 });
      } catch (e) {
        console.warn('[home._checkSwitchAndNavigate] switch check failed:', e);
        // 请求失败默认开启，避免误封
        const sw = Object.assign({}, this.data._featureSwitches, { [code]: { is_enabled: true, tip_message: '' } });
        const ts2 = Object.assign({}, this.data._featureSwitchesTS, { [code]: now });
        this.setData({ _featureSwitches: sw, _featureSwitchesTS: ts2 });
      }
    }
    const current = this.data._featureSwitches[code];
    console.log('[home._checkSwitchAndNavigate] current switch:', current);
    if (!current.is_enabled) {
      this.showError(current.tip_message || '该功能已关闭，请联系管理员开启');
      return;
    }
    if (beforeNavigate) {
      const ok = await beforeNavigate();
      if (!ok) return;
    }
    console.log('[home._checkSwitchAndNavigate] navigateTo', targetUrl);
    // 兜底重试：分包 navigateTo 在开发者工具 1.06+ 偶发 timeout，
    // 第一次失败后等 300ms 再重试一次，绝大多数情况能成功
    const tryNavigate = (attempt) => {
      wx.navigateTo({
        url: targetUrl,
        success: () => {
          console.log('[home._checkSwitchAndNavigate] navigateTo success', targetUrl);
        },
        fail: (err) => {
          console.error('[home._checkSwitchAndNavigate] navigateTo fail (attempt', attempt, '):', err);
          if (attempt < 2 && err && err.errMsg && err.errMsg.includes('timeout')) {
            // 分包下载超时，等一会再重试（分包大概率已经下完了）
            setTimeout(() => tryNavigate(attempt + 1), 300);
          } else {
            const msg = (err && err.errMsg && err.errMsg.includes('timeout'))
              ? '页面加载超时，请检查网络后重试'
              : '页面打开失败，请稍后重试';
            this.showError(msg);
          }
        }
      });
    };
    tryNavigate(1);
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad(options) {
    this.getNotices();

    const windowInfo = wx.getWindowInfo();
    const screenWidth = windowInfo.windowWidth;
    const screenHeight = windowInfo.windowHeight;
    const btnWidth = 140 * (screenWidth / 750);

    this.setData({
      screenWidth: screenWidth,
      screenHeight: screenHeight,
      registerBtnX: screenWidth - btnWidth,
      registerBtnY: screenHeight - 320
    });

    // 启动数字滚动动画
    this.animateNumbers();

    // 初始化重要通知显示状态（用户关闭后 1 天内不再显示）
    this.initImportantNotice();
  },

  // 初始化重要通知（默认显示；用户点过关闭，则 1 天内不显示）
  initImportantNotice() {
    // TODO: 明年 9 月开放给新生用（2027-09-01 起启用），届时删除这段判断
    const NOTICE_AVAILABLE_AT = new Date('2027-09-01T00:00:00').getTime();
    if (Date.now() < NOTICE_AVAILABLE_AT) {
      this.setData({ showImportantNotice: false });
      return;
    }

    try {
      const closedAt = wx.getStorageSync('important_notice_closed_at');
      const ONE_DAY = 24 * 60 * 60 * 1000;
      if (closedAt && (Date.now() - Number(closedAt)) < ONE_DAY) {
        this.setData({ showImportantNotice: false });
        return;
      }
    } catch (_) {}
    // 显示当前日期（YYYY-MM-DD）
    const now = new Date();
    const pad = (n) => (n < 10 ? '0' + n : '' + n);
    const dateStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    this.setData({
      showImportantNotice: true,
      importantNoticeDate: dateStr,
    });
  },

  // 点击整张通知卡片
  onTapImportantNotice() {
    // 跳转到中职新生缴费页（与通知内容关联：缴费完成自动生成录取通知书）
    this._checkSwitchAndNavigate('zzpay', '/packageVocational/pages/vocational-new-payment/vocational-new-payment');
  },

  // 关闭重要通知（24h 内不再显示）
  onCloseImportantNotice() {
    try {
      wx.setStorageSync('important_notice_closed_at', Date.now());
    } catch (_) {}
    this.setData({ showImportantNotice: false });
  },

  /**
   * 生命周期函数--监听页面初次渲染完成
   */
  onReady() {
    this.observeStatsBar();
  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow() {
    // 用户从子页面返回首页：清掉开关缓存，下次点击重新问后端
    // 这样管理员改了 DB 的 is_enabled，用户下一次点击就能立即感知
    // 用 _featureSwitchesVersion 计数器判断是否非首次显示（避免 NaN 比较陷阱）
    const ver = this.data._featureSwitchesVersion || 0;
    if (ver > 0) {
      this.setData({
        _featureSwitches: {},
        _featureSwitchesTS: {},
        _featureSwitchesVersion: ver + 1,
      });
    } else {
      // 首次显示：仅初始化版本号（不调 setData 避免无意义的渲染）
      this.data._featureSwitchesVersion = 1;
    }
  },

  /**
   * 生命周期函数--监听页面隐藏
   */
  onHide() {

  },

  /**
   * 生命周期函数--监听页面卸载
   */
  onUnload() {
    if (this._animTimer) {
      clearInterval(this._animTimer);
    }
    if (this._statsObserver) {
      this._statsObserver.disconnect();
    }
  },

  /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh() {

  },

  /**
   * 页面上拉触底事件的处理函数
   */
  onReachBottom() {

  },

  /**
   * 用户点击右上角分享
   */
  onShareAppMessage() {

  },

  // 数字滚动动画
  animateNumbers() {
    // 如果有正在运行的动画，先清除
    if (this._animTimer) {
      clearInterval(this._animTimer);
    }

    // 先归零
    this.setData({
      animatedYear: 0,
      animatedStudents: 0,
      animatedTotal: 0
    });

    const targets = { year: 1979, students: 5000, total: 48000 };
    const duration = 1500;
    const fps = 30;
    const frames = Math.ceil(duration / (1000 / fps));
    let frame = 0;

    this._animTimer = setInterval(() => {
      frame++;
      const progress = frame / frames;
      const ease = 1 - Math.pow(1 - progress, 3);

      this.setData({
        animatedYear: Math.round(ease * targets.year),
        animatedStudents: Math.round(ease * targets.students),
        animatedTotal: Math.round(ease * targets.total)
      });

      if (frame >= frames) {
        clearInterval(this._animTimer);
        this._animTimer = null;
        this.setData({
          animatedYear: targets.year,
          animatedStudents: targets.students,
          animatedTotal: targets.total
        });
      }
    }, 1000 / fps);
  },

  // 点击统计条重新播放动画
  onStatsTap() {
    this.animateNumbers();
  },

  // 监听统计条滚入视口，重新播放动画
  observeStatsBar() {
    this._statsObserver = this.createIntersectionObserver();
    this._statsObserver.relativeToViewport({ bottom: 0 }).observe('.stats-bar', (res) => {
      if (res.intersectionRatio > 0) {
        this.animateNumbers();
      }
    });
  },

  getNotices() {
    // TODO: 从服务器获取通知列表
  },

  // 导航点击处理
  onNavItemTap(e) {
    const type = e.currentTarget.dataset.type;
    
    switch(type) {
      case 'intro':
        wx.navigateTo({
          url: '/pages/intro/intro',
          fail: (err) => {
            console.error('跳转失败:', err);
          }
        });
        break;
      case 'enroll':
        wx.navigateTo({
          url: '/packageEnroll/pages/enroll-guide/enroll-guide',
          fail: (err) => {
            console.error('跳转失败:', err);
          }
        });
        break;
      case 'qa':
        wx.navigateTo({
          url: '/packageOther/pages/qa/qa',
          fail: (err) => {
            console.error('跳转失败:', err);
          }
        });
        break;
      case 'student_info':
        wx.navigateTo({
          url: '/packageStudent/pages/student-info/student-info',
          fail: (err) => {
            console.error('跳转失败:', err);
          }
        });
        break;
      case 'promotion_qr':
        wx.navigateTo({
          url: '/packageStudent/pages/student-info/student-info',
          fail: (err) => {
            console.error('跳转失败:', err);
          }
        });
        break;
    }
  },


  // 开放新生缴费跳转
  goToNewStudentPayment() {
    this._checkSwitchAndNavigate('kfpay', '/packageEnroll/pages/new-student-payment/new-student-payment');
  },

  // 中职教育新生报名跳转（兼容旧接口：报名开关在新表lw_feature_switch）
  async goToNewZZStudentSignUp() {
    this._checkSwitchAndNavigate('zzbm', '/packageVocational/pages/vocational-zzbm/vocational-zzbm');
  },

  // 中职教育新生缴费跳转
  goToNewZZStudentPayment() {
    this._checkSwitchAndNavigate('zzpay', '/packageVocational/pages/vocational-new-payment/vocational-new-payment');
  },

  // 问卷调查跳转
  goToSurveyList() {
    wx.navigateTo({
      url: '/packageSurvey/pages/survey-list/survey-list',
      fail: (err) => {
        console.error('[home.goToSurveyList] fail:', err);
        this.showError('页面打开失败，请稍后重试');
      }
    });
  },

  // 校园反馈跳转（去掉开关检查，直接跳转）
  goToFeedback() {
    // 直接跳转到 feedback-login，跳过 feedback-submit 的二次跳转逻辑
    const targetUrl = '/packageAdmin/pages/feedback-login/feedback-login?redirect=' +
      encodeURIComponent('/packageAdmin/pages/feedback-submit/feedback-submit');
    const tryNavigate = (attempt) => {
      wx.navigateTo({
        url: targetUrl,
        success: () => console.log('[home.goToFeedback] navigateTo success'),
        fail: (err) => {
          console.warn('[home.goToFeedback] navigateTo fail (attempt', attempt, '):', err);
          if (attempt < 2) {
            // 重试一次（开发者工具偶发的 timeout，重试大概率成功）
            setTimeout(() => tryNavigate(attempt + 1), 500);
          } else {
            // navigateTo 多次失败，降级为 redirectTo（不增加页面栈，开发者工具上更稳定）
            console.log('[home.goToFeedback] fallback to redirectTo');
            wx.redirectTo({
              url: targetUrl,
              fail: (err2) => {
                console.error('[home.goToFeedback] redirectTo also fail:', err2);
                this.showError('页面打开失败，请稍后重试');
              }
            });
          }
        }
      });
    };
    tryNavigate(1);
  },

  // 考试小程序入口（独立实现，不复用现有 exame-list）
  goToExameMini() {
    wx.navigateTo({
      url: '/packageExame/pages/mini-login/mini-login',
      fail: (err) => {
        console.warn('[home.goToExameMini] fail:', err);
        wx.redirectTo({
          url: '/packageExame/pages/mini-login/mini-login',
          fail: (err2) => {
            console.error('[home.goToExameMini] redirectTo also fail:', err2);
            this.showError('页面打开失败，请稍后重试');
          }
        });
      }
    });
  },

  // 管理中心跳转
  goToAdminNav() {
    this._checkSwitchAndNavigate('admin', '/packageAdmin/pages/admin-nav/admin-nav');
  },

  // 电表充值跳转（输入电表名 → 完全匹配 → 展示二维码）
  goToMeterRecharge() {
    this._checkSwitchAndNavigate('dianbiao', '/pages/meter-recharge/meter-recharge');
  },
  





  
  // 招生简章跳转
  goToEnroll() {
    wx.navigateTo({
      url: '/pages/enroll/enroll'
    });
  },

  // 播放视频
  playVideo() {
    wx.createVideoContext('promoVideo').requestFullScreen();
    wx.navigateTo({
      url: '/packageOther/pages/video-player/video-player',
      success: (res) => {
        // 可以通过 eventChannel 向被打开页面传送数据
        res.eventChannel.emit('acceptDataFromOpenerPage', {
          videoUrl: 'your-video-url-here',  // 替换为实际的视频URL
          videoTitle: '平凡中育非凡',
          videoSubtitle: '江苏开放大学招生宣传片'
        });
      }
    });
  },

  // 打开视频播放页面
  openVideo() {
    wx.navigateTo({
      url: '/packageOther/pages/video-player/video-player',
      success: (res) => {
        res.eventChannel.emit('acceptDataFromOpenerPage', {
          finderUserName: this.data.finderUserName,
          feedId: this.data.feedId
        });
      }
    });
  },

  // 关闭视频
  closeVideo() {
    // 不再需要此方法，可以删除
  },

  goToNewStudentSignUp() {
    this._checkSwitchAndNavigate('kfbm', '/pages/enrollment-webview/enrollment-webview');
  },

  // 关闭图片预览
  closeSignUpImage() {
    this.setData({
      showSignUpImage: false
    });
  },









  // 长按图片保存/转发
  onLongPressSignUpImage() {
    const url = this.data.signUpImageUrl;
    wx.showActionSheet({
      itemList: ['保存到相册', '转发给朋友'],
      success: (res) => {
        if (res.tapIndex === 0) {
          // 保存到相册
          wx.saveImageToPhotosAlbum({
            filePath: url,
            success: () => {
              wx.showToast({ title: '已保存到相册', icon: 'success' });
            },
            fail: () => {
              wx.showToast({ title: '保存失败', icon: 'none' });
            }
          });
        } else if (res.tapIndex === 1) {
          // 转发
          wx.previewImage({
            urls: [url]
          });
        }
      }
    });
  },

  handleRegisterBtnChange(e) {
    this.currentRegisterBtnX = e.detail.x;
    this.currentRegisterBtnY = e.detail.y;
  },

  handleRegisterBtnTouchEnd() {
    const x = this.currentRegisterBtnX || this.data.registerBtnX;
    const y = this.currentRegisterBtnY || this.data.registerBtnY;
    const { screenWidth, screenHeight } = this.data;

    const btnSize = 120 * (screenWidth / 750);
    const safeBottom = 240 * (screenWidth / 750); // 底部 tabBar 安全区
    const safeTop = 80 * (screenWidth / 750);     // 顶部状态栏安全区

    let targetX;
    const centerX = screenWidth / 2;
    if (x < centerX) {
      targetX = 0;
    } else {
      targetX = screenWidth - btnSize;
    }

    // Y 方向边界限制：不能超出安全可视区
    let targetY = y;
    if (targetY < safeTop) targetY = safeTop;
    if (targetY > screenHeight - safeBottom - btnSize) {
      targetY = screenHeight - safeBottom - btnSize;
    }

    this.setData({
      registerBtnX: targetX,
      registerBtnY: targetY
    });
  },

  handleRegisterBtnTap() {
    this._checkSwitchAndNavigate('job', '/packageStudent/pages/job-recommend/job-recommend');
  },

  // 时间窗口校验（点击入口时检查；不在窗口内则提示并阻止跳转）
  // 返回 Promise<boolean>：true=通过可跳转，false=被拦截
  // 兼容旧用法：可传入 callback，校验结束时调用 callback(true|false)
  async _checkCategoryWindowThenNavigate(infoUrl, targetUrl, callback) {
    let ok = false;
    try {
      const info = await get(infoUrl, {}, { showLoading: false });
      const result = evaluateWindow({
        is_active: info.is_active !== false,
        start_time: info.start_time,
        end_time: info.end_time,
        batch: info.batch
      });
      if (!result.ok) {
        this.showError(result.message);
        ok = false;
      } else {
        ok = true;
      }
    } catch (e) {
      this.showError(e && e.message ? e.message : '加载失败，请稍后再试');
      ok = false;
    }
    // 兼容历史调用：有的地方传入 callback，这里统一调用
    if (typeof callback === 'function') {
      try { callback(ok); } catch (_) {}
    }
    return ok;
  },

  // 3+4报名跳转
  goToThreePlusFourRegister() {
    this._checkSwitchAndNavigate('34', '/packageEnroll/pages/three-plus-four-register/three-plus-four-register', async () => {
      return await this._checkCategoryWindowThenNavigate(
        '/vocational34/prospectus',
        '/packageEnroll/pages/three-plus-four-register/three-plus-four-register'
      );
    });
  },

  // 成人教育报名跳转
  goToAdultExamEnroll() {
    this._checkSwitchAndNavigate('adult', '/packageEnroll/pages/adult-exam-enroll/adult-exam-enroll', async () => {
      return await this._checkCategoryWindowThenNavigate(
        '/enrollment/prospectus?code=adult_exam',
        '/packageEnroll/pages/adult-exam-enroll/adult-exam-enroll'
      );
    });
  },

  // 毕业生就业调查跳转
  goToGraduateEmploymentSurvey() {
    this._checkSwitchAndNavigate('graduate', '/packageStudent/pages/graduate-employment-survey/graduate-employment-survey', async () => {
      return await this._checkCategoryWindowThenNavigate(
        '/grad_emp_survey/info',
        '/packageStudent/pages/graduate-employment-survey/graduate-employment-survey'
      );
    })
  },

  // ============================================================
  // 问卷填写临时测试入口已下线
  // ============================================================
})