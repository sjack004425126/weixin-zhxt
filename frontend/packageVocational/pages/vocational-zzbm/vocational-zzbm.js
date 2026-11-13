const app = getApp();
const { decodeUrlSafeBase64 } = require("../../../utils/base64.js");
const { createPage } = require('../../../utils/page-mixin');
const { get, post } = require('../../../utils/request');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');


createPage({
  data: {
    bmxs: {
      bdzy: null,
      byxxmc: "",
      byxxssx1: "",
      byxxssx2: "",
      byxxssx3: "",
      hkxz: "",
      id: null,
      jtxxdz: "",
      jzdh: "",
      jzdlx: null,
      jzgx: "",
      jzxm: "",
      mz: "",
      pc: null,
      qd: null,
      qdjs: "",
      sfjdlk: "",
      sflset: 0,
      sftwjrzn: 0,
      sfqdxf: null,
      sfzh: "",
      tjsj: null,
      xb: "",
      xm: "",
      xsdh: "",
      xsly: "",
      zsdx: null,
      zzmm: null,
      remark: "",
      is_complete: 0
    },

    // 介绍人相关数据
    showIntroducerPopup: false,
    introducerSearchKeyword: '',
    selectedAlphabet: '全部',
    alphabetList: ['全部', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'],
    introducerList: [
      { name: '王小华', pinyin: 'WXH', firstLetter: 'W', avatar: '王' },
      { name: '张龙', pinyin: 'ZL', firstLetter: 'Z', avatar: '张' },
      { name: '杨欢', pinyin: 'YH', firstLetter: 'Y', avatar: '杨' },
      { name: '潘明月', pinyin: 'PMY', firstLetter: 'P', avatar: '潘' },
      { name: '杨仁伟', pinyin: 'YRW', firstLetter: 'Y', avatar: '杨' },
      { name: '李聪聪', pinyin: 'LCC', firstLetter: 'L', avatar: '李' },
      { name: '钟卫东', pinyin: 'ZWD', firstLetter: 'Z', avatar: '钟' },
      { name: '余勇', pinyin: 'YY', firstLetter: 'Y', avatar: '余' },
      { name: '文肇', pinyin: 'WZ', firstLetter: 'W', avatar: '文' },
      { name: '鄢汉萍', pinyin: 'YHP', firstLetter: 'Y', avatar: '鄢' },
      { name: '文松萍', pinyin: 'WSP', firstLetter: 'W', avatar: '文' },
      { name: '龙艳香', pinyin: 'LYX', firstLetter: 'L', avatar: '龙' },
      { name: '杨铠伊', pinyin: 'YKY', firstLetter: 'Y', avatar: '杨' },
      { name: '王雪梅', pinyin: 'WXM', firstLetter: 'W', avatar: '王' },
      { name: '杨旭', pinyin: 'YX', firstLetter: 'Y', avatar: '杨' },
      { name: '周文伟', pinyin: 'ZWW', firstLetter: 'Z', avatar: '周' },
      { name: '尹慧', pinyin: 'YH', firstLetter: 'Y', avatar: '尹' },
      { name: '袁婷', pinyin: 'YT', firstLetter: 'Y', avatar: '袁' },
      { name: '朱彦蓉', pinyin: 'ZYR', firstLetter: 'Z', avatar: '朱' },
      { name: '陈方静怡', pinyin: 'CFJY', firstLetter: 'C', avatar: '陈' },
      { name: '植凤萍', pinyin: 'ZFP', firstLetter: 'Z', avatar: '植' },
      { name: '杨颜萍', pinyin: 'YYP', firstLetter: 'Y', avatar: '杨' },
      { name: '龙淇', pinyin: 'LQ', firstLetter: 'L', avatar: '龙' },
      { name: '刘荣枝', pinyin: 'LRZ', firstLetter: 'L', avatar: '刘' },
      { name: '王在珣', pinyin: 'WZX', firstLetter: 'W', avatar: '王' },
      { name: '蔡代娇', pinyin: 'CDJ', firstLetter: 'C', avatar: '蔡' },
      { name: '白银坪', pinyin: 'BYP', firstLetter: 'B', avatar: '白' },
      { name: '童怡昕', pinyin: 'TYX', firstLetter: 'T', avatar: '童' },
      { name: '龙明杰', pinyin: 'LMJ', firstLetter: 'L', avatar: '龙' },
      { name: '刘嘉丽', pinyin: 'LJL', firstLetter: 'L', avatar: '刘' },
      { name: '韦兴燕', pinyin: 'WXY', firstLetter: 'W', avatar: '韦' },
      { name: '杨帆', pinyin: 'YF', firstLetter: 'Y', avatar: '杨' },
      { name: '王琳', pinyin: 'WL', firstLetter: 'W', avatar: '王' },
      { name: '高杰', pinyin: 'GJ', firstLetter: 'G', avatar: '高' },
      { name: '夏晓刚', pinyin: 'XXG', firstLetter: 'X', avatar: '夏' },
      { name: '龙开星', pinyin: 'LKX', firstLetter: 'L', avatar: '龙' },
      { name: '霍永生', pinyin: 'HYS', firstLetter: 'H', avatar: '霍' },
      { name: '杨顺波', pinyin: 'YSB', firstLetter: 'Y', avatar: '杨' },
      { name: '王正仿', pinyin: 'WZF', firstLetter: 'W', avatar: '王' },
      { name: '罗文雯', pinyin: 'LWW', firstLetter: 'L', avatar: '罗' },
      { name: '杨敏', pinyin: 'YM', firstLetter: 'Y', avatar: '杨' },
      { name: '周桂珍', pinyin: 'ZGZ', firstLetter: 'Z', avatar: '周' },
      { name: '龙安发', pinyin: 'LAF', firstLetter: 'L', avatar: '龙' },
      { name: '喻双', pinyin: 'YS', firstLetter: 'Y', avatar: '喻' },
      { name: '王秀君', pinyin: 'WXJ', firstLetter: 'W', avatar: '王' },
      { name: '吴兴递', pinyin: 'WXD', firstLetter: 'W', avatar: '吴' },
      { name: '吴仙燕', pinyin: 'WXY', firstLetter: 'W', avatar: '吴' },
      { name: '张仕强', pinyin: 'ZSQ', firstLetter: 'Z', avatar: '张' },
      { name: '刘敏', pinyin: 'LM', firstLetter: 'L', avatar: '刘' },
      { name: '潘燕林', pinyin: 'PYL', firstLetter: 'P', avatar: '潘' },
      { name: '杨鹏', pinyin: 'YP', firstLetter: 'Y', avatar: '杨' },
      { name: '欧阳可珍', pinyin: 'OYKZ', firstLetter: 'O', avatar: '欧' },
      { name: '彭旺', pinyin: 'PW', firstLetter: 'P', avatar: '彭' },
      { name: '潘淼', pinyin: 'PM', firstLetter: 'P', avatar: '潘' },
      { name: '王东', pinyin: 'WD', firstLetter: 'W', avatar: '王' },
      { name: '姚荣珊', pinyin: 'YRS', firstLetter: 'Y', avatar: '姚' },
      { name: '杨升敏', pinyin: 'YSM', firstLetter: 'Y', avatar: '杨' },
      { name: '杨泽', pinyin: 'YZ', firstLetter: 'Y', avatar: '杨' },
      { name: '潘永成', pinyin: 'PYC', firstLetter: 'P', avatar: '潘' },
      { name: '周昌松', pinyin: 'ZCS', firstLetter: 'Z', avatar: '周' },
      { name: '高亮', pinyin: 'GL', firstLetter: 'G', avatar: '高' },
      { name: '莫福梅', pinyin: 'MFM', firstLetter: 'M', avatar: '莫' },
      { name: '李瑶瑶', pinyin: 'LYY', firstLetter: 'L', avatar: '李' },
      { name: '袁杨成', pinyin: 'YYC', firstLetter: 'Y', avatar: '袁' },
      { name: '吴培英', pinyin: 'WPY', firstLetter: 'W', avatar: '吴' },
      { name: '吴化仙', pinyin: 'WHX', firstLetter: 'W', avatar: '吴' },
      { name: '肖祖芳', pinyin: 'XZF', firstLetter: 'X', avatar: '肖' },
      { name: '杨秀斌', pinyin: 'YXB', firstLetter: 'Y', avatar: '杨' },
      { name: '王仁倩', pinyin: 'WRQ', firstLetter: 'W', avatar: '王' },
      { name: '杨瑞瑶', pinyin: 'YRY', firstLetter: 'Y', avatar: '杨' },
      { name: '吴敏茜', pinyin: 'WMQ', firstLetter: 'W', avatar: '吴' },
      { name: '陈慧', pinyin: 'CH', firstLetter: 'C', avatar: '陈' },
      { name: '林泽鸿', pinyin: 'LZH', firstLetter: 'L', avatar: '林' },
      { name: '郑洁洁', pinyin: 'ZJJ', firstLetter: 'Z', avatar: '郑' },
      { name: '陆大富', pinyin: 'LDF', firstLetter: 'L', avatar: '陆' },
      { name: '王一珏', pinyin: 'WYJ', firstLetter: 'W', avatar: '王' },
      { name: '杨天嫄', pinyin: 'YTY', firstLetter: 'Y', avatar: '杨' },
      { name: '陈文龙', pinyin: 'CWL', firstLetter: 'C', avatar: '陈' },
      { name: '蒋昌容', pinyin: 'JCR', firstLetter: 'J', avatar: '蒋' },
      { name: '王明灯', pinyin: 'WMD', firstLetter: 'W', avatar: '王' },
      { name: '邓力', pinyin: 'DL', firstLetter: 'D', avatar: '邓' },
      { name: '吴光文', pinyin: 'WGW', firstLetter: 'W', avatar: '吴' },
      { name: '彭泽伟', pinyin: 'PZW', firstLetter: 'P', avatar: '彭' },
      { name: '张忠标', pinyin: 'ZZB', firstLetter: 'Z', avatar: '张' },
      { name: '孙正飞', pinyin: 'SZF', firstLetter: 'S', avatar: '孙' },
      { name: '石开华', pinyin: 'SKH', firstLetter: 'S', avatar: '石' },
      { name: '池穆朗', pinyin: 'CML', firstLetter: 'C', avatar: '池' },
      { name: '李媛媛', pinyin: 'LYY', firstLetter: 'L', avatar: '李' },
      { name: '杨宗振', pinyin: 'YZZ', firstLetter: 'Y', avatar: '杨' },
      { name: '李永睿', pinyin: 'LYR', firstLetter: 'L', avatar: '李' },
      { name: '李国榕', pinyin: 'LGR', firstLetter: 'L', avatar: '李' },
      { name: '粟多铭', pinyin: 'SDM', firstLetter: 'S', avatar: '粟' },
      { name: '王明勇', pinyin: 'WMY', firstLetter: 'W', avatar: '王' },
      { name: '王晋伟', pinyin: 'WJW', firstLetter: 'W', avatar: '王' },
      { name: '王昕', pinyin: 'WX', firstLetter: 'W', avatar: '王' },
      { name: '黄功琴', pinyin: 'HGQ', firstLetter: 'H', avatar: '黄' },
      { name: '杨家平', pinyin: 'YJP', firstLetter: 'Y', avatar: '杨' },
      { name: '封璇', pinyin: 'FX', firstLetter: 'F', avatar: '封' },
      { name: '段忠贵', pinyin: 'DZG', firstLetter: 'D', avatar: '段' },
      { name: '潘柳松', pinyin: 'PLS', firstLetter: 'P', avatar: '潘' },
      { name: '吴如金', pinyin: 'WRJ', firstLetter: 'W', avatar: '吴' },
      { name: '包琳恩', pinyin: 'BLE', firstLetter: 'B', avatar: '包' },
      { name: '韦国睿', pinyin: 'WGR', firstLetter: 'W', avatar: '韦' },
      { name: '杨百忠', pinyin: 'YBZ', firstLetter: 'Y', avatar: '杨' },
      { name: '杨亚群', pinyin: 'YYQ', firstLetter: 'Y', avatar: '杨' },
      { name: '姜魁', pinyin: 'JK', firstLetter: 'J', avatar: '姜' },
      { name: '田锦友', pinyin: 'TJY', firstLetter: 'T', avatar: '田' },
      { name: '杨熠', pinyin: 'YY', firstLetter: 'Y', avatar: '杨' },
      { name: '周明菲', pinyin: 'ZMF', firstLetter: 'Z', avatar: '周' },
      { name: '杨军', pinyin: 'YJ', firstLetter: 'Y', avatar: '杨' }
    ],
    filteredIntroducers: [],

    // 推广相关状态
    isPromotionEntry: false, // 是否通过推广链接进入
    promotionIntroducer: '', // 推广介绍人

    // 保存原始的报考学校及专业数据用于联动的检索
    bdzys: null,
    // 实时名额映射：{ majorId: remaining }，由 loadBdzyList 填充，供 _buildSchoolList 使用
    majorRemainingMap: {},

    // 性别
    xbArray: ['男', '女'],
    xbIndex: null,

    // 民族
    mzArray: ["汉族","苗族","侗族","水族","布依族","仡佬族","壮族","满族","回族","维吾尔族","土家族","彝族","蒙古族","藏族","瑶族","朝鲜族","白族","哈尼族","哈萨克族","黎族","傣族","畲族","傈僳族","东乡族","高山族","拉祜族","佤族","纳西族","羌族","土族","仫佬族","锡伯族","柯尔克孜族","达斡尔族","景颇族","毛南族","撒拉族","布朗族","塔吉克族","阿昌族","普米族","鄂温克族","怒族","京族","基诺族","德昂族","保安族","俄罗斯族","裕固族","乌孜别克族","门巴族","鄂伦春族","独龙族","塔塔尔族","赫哲族","珞巴族","穿青人族","其他","外国血统中国籍人士"],
    mzIndex: null,

    // 政治面貌 - 名称数组与 id 数组分开保存，避免与后端数据库 ID 错位
    zzmmArray: [],
    zzmmIdArray: [],
    zzmmIndex: null,


    // 户口类型
    hkxzArray: ['农业户口', '非农业户口'],
    hkxzIndex: null,

    // 是否建档立卡
    sfjdlkArray: ['否', '是'],
    sfjdlkIndex: null,


    // 是否留守儿童
    sflsetArray: ['否', '是'],
    sflsetIndex: null,


    // 与家长关系 - name + id 双数组
    jzgxArray: [],
    jzgxIdArray: [],
    jzgxIndex: null,


    // 居住地类型 - name + id 双数组
    jzdlxArray: [],
    jzdlxIdArray: [],
    jzdlxIndex: null,


    // 招生对象 - name + id 双数组
    zsdxArray: [],
    zsdxIdArray: [],
    zsdxIndex: null,


    // 渠道 - name + id 双数组
    qdArray: [],
    qdIdArray: [],
    qdIndex: null,


    // 招生来源
    zslyArray: ['志愿填报', '非志愿填报'],
    zslyIndex: null,

    // 是否购买校服选项
    sfArray: ['否', '是'],
    sfqdxfIndex: null,

    // 报考学校及专业
    bdzyArray:  [[], []],
    bdzyIndex: [],

    // 专业选择自定义弹出层
    showMajorPickerPopup: false,
    tempCatIndex: 0,
    tempSchoolList: [],

    address: ['贵州省','黔东南苗族侗族自治州','凯里市'],
    submitDisabled: false,

    // 报名成功弹窗
    showSuccessModal: false,
    successQueryCode: '',
    successMajorName: '',
    isNewRegistration: false, // 是否是新报名（抢占名额成功后弹窗）

    // 编辑模式相关
    isEditMode: false,
    editRecordId: null,
    editQueryCode: '',
    originalBdzy: null, // 记录原始专业，用于判断是否修改
    paymentInfo: null,

    // 剩余名额
    remaining: null,

    // 报名记录ID（预创建后保存）
    enrollmentId: null,

    // 步骤向导
    currentStep: 0,
    stepList: ['身份', '专业', '基本', '家庭', '校服', '招生'],

    // 已报名用户身份二次验证（手机号验证码）
    showVerifyCodeModal: false,    // 是否显示手机号快捷认证弹窗
    verifyRole: '',               // self/parent
    verifyRoleToken: '',          // 后端返回的 verify_token
    verifyRoleMaskedPhone: '',    // 138****1234
    verifyRoleTypeText: '',       // '本人手机号' / '家长手机号'
    verifyRolePassed: false,      // 是否已通过身份验证
    verifyRoleVerifying: false,   // 请求中（按钮 disabled + loading）
    verifyToken: '',               // 验证通过后获得的 token（15 分钟有效）
  },

  onLoad(options) {
    // 二次判断：即使通过首页入口进来了，仍检查开关
    checkFeatureSwitch('zzbm', this);

    this.getBmxsInfo()
    this.loadFormData()
    this.filterIntroducers() // 初始化介绍人列表
    this.handlePromotionParams(options);
  },

  // ── 获取用户标识：只用 openid_code（新生匿名），无其他回退 ──
  async _getUserKey() {
    if (app.globalData.openidCode) return app.globalData.openidCode;
    try {
      const code = await app.getOpenid_code();
      if (code) {
        app.globalData.openidCode = code;
        return code;
      }
    } catch (_) {}
    return '';
  },

  // 下一步（含当前步骤校验）
  async nextStep() {
    const step = this.data.currentStep;
    const bmxs = this.data.bmxs;

    // 第一步：身份证和电话
    if (step === 0) {
      if (!bmxs.sfzh) {
        this.showError('请填写身份证号');
        return;
      }
      if (!this.isIDCard(bmxs.sfzh)) {
        this.showError('身份证号格式不正确');
        return;
      }
      if (!bmxs.xsdh) {
        this.showError('请填写学生电话');
        return;
      }
      const phoneReg = /^1[3-9]\d{9}$/;
      if (!phoneReg.test(bmxs.xsdh)) {
        this.showError('学生电话格式不正确');
        return;
      }

      wx.showLoading({ title: '检查中...' });
      try {
        const checkData = await get('/zzbm/check_enrolled', { sfzh: bmxs.sfzh.toUpperCase() }, { showLoading: false });
        wx.hideLoading();

        // 后端统一返回 {bm: true/false}：true=已报名（编辑模式），false=未报名（新报名模式）
        if (checkData && checkData.bm === true) {
          // 已报名：必须先通过报名手机号短信验证才能进入编辑模式
          // 防止他人盗用身份证号修改他人信息
          // 先查本地缓存：同身份证号在有效期内已验证过，则直接复用，跳过弹窗
          const cached = this._readVerifyCache(bmxs.sfzh.toUpperCase());
          if (cached && cached.verifyToken) {
            this.setData({ verifyToken: cached.verifyToken });
            await this._loadEnrolledAndEnterStep1();
          } else {
            // 没有缓存或缓存不匹配 → 弹窗让用户输入验证码
            const verifyPassed = await this._requireEnrollmentVerifyCode();
            if (verifyPassed && this.data.verifyToken) {
              await this._loadEnrolledAndEnterStep1();
            }
            // 验证失败 / 用户取消：留在 step 0
          }
        } else {
          this.setData({ isEditMode: false, isNewRegistration: false });
          const loaded = await this.loadBdzyList();
          if (!loaded) {
            this.showError('专业数据加载失败，请稍后重试');
            return;
          }
          wx.showToast({ title: '未检测到报名记录（新报名模式）', icon: 'success' });
          this.setData({ currentStep: 1 });
        }
        return;  // step 0 的目标步骤已在分支内显式设置，避免被末尾 step+1 覆盖
      } catch (e) {
        wx.hideLoading();
        const errMsg = (typeof e === 'string' && e) ? e : (e && e.msg) ? e.msg : '网络异常，请稍后重试';
        this.showError(errMsg);
        return;
      }
    } else if (step === 1) {
      // 第二步：选专业
      // 编辑模式：检查专业变更（名额校验 + 提交后端）
      if (this.data.isEditMode) {
        const originalBdzy = this.data.originalBdzy;

        if (!originalBdzy && !bmxs.bdzy) {
          this.showError('请选择报读专业和贯通院校');
          return;
        }

        // 校验变更：检查新专业名额
        const changed = originalBdzy && bmxs.bdzy && String(originalBdzy) !== String(bmxs.bdzy);
        if (changed) {
          const latestRemaining = await this.fetchLatestRemaining(bmxs.bdzy);
          if (latestRemaining !== null && latestRemaining <= 0) {
            this.showError('名额已满，请选择其他专业');
            const catIdx = (this.data.bdzyIndex && this.data.bdzyIndex.length > 0) ? this.data.bdzyIndex[0] : 0;
            const refreshedList = this._buildSchoolList(catIdx);
            this.setData({
              showMajorPickerPopup: true,
              tempCatIndex: catIdx,
              tempSchoolList: refreshedList
            });
            return;
          }
          // 立即提交专业变更到后端
          wx.showLoading({ title: '修改专业中...' });
          try {
            const updateRes = await post('/zzbm/update_info', {
              id: this.data.enrollmentId,
              bdzy: bmxs.bdzy
            }, { showLoading: false });
            wx.hideLoading();
            if (!updateRes || updateRes.success === false) {
              const errMsg = (updateRes && updateRes.msg) ? updateRes.msg : '修改专业失败，请重试';
              this.showError(errMsg);
              return;
            }
            wx.showToast({ title: '专业已修改', icon: 'success' });
            // 已同步到后端，更新 originalBdzy，避免被当作"还会变"
            this.setData({ originalBdzy: bmxs.bdzy });
          } catch (e) {
            wx.hideLoading();
            const errMsg = (typeof e === 'string' && e) ? e : (e && e.msg) ? e.msg : '修改专业失败，请重试';
            this.showError(errMsg);
            return;
          }
        } else if (!originalBdzy && bmxs.bdzy) {
          // 没有原始专业但选了新专业（极少见，作为新报名兜底）
          const latestRemaining = await this.fetchLatestRemaining(bmxs.bdzy);
          if (latestRemaining !== null && latestRemaining <= 0) {
            this.showError('名额已满，请选择其他专业');
            const catIdx = (this.data.bdzyIndex && this.data.bdzyIndex.length > 0) ? this.data.bdzyIndex[0] : 0;
            const refreshedList = this._buildSchoolList(catIdx);
            this.setData({
              showMajorPickerPopup: true,
              tempCatIndex: catIdx,
              tempSchoolList: refreshedList
            });
            return;
          }
        }
        this.saveFormData();
      } else {
        // 新报名模式：检查是否选了专业
        if (!bmxs.bdzy) {
          this.showError('请选择报读专业');
          return;
        }
        // 抢占名额
        wx.showLoading({ title: '抢占名额中...' });
        try {
          const result = await post('/zzbm/pre_create', {
            sfzh: bmxs.sfzh.toUpperCase(),
            xsdh: bmxs.xsdh,
            bdzy: String(bmxs.bdzy)
          }, { showLoading: false });
          wx.hideLoading();
          if (!result || !result.id) {
            const errMsg = (result && result.msg) ? result.msg : '抢占名额失败，请重试';
            this.showError(errMsg);
            return;
          }
          this.setData({
            enrollmentId: result.id,
            isNewRegistration: true,
            successQueryCode: result.query_code || ''
          });
          wx.showToast({ title: '名额抢占成功', icon: 'success' });
        } catch (e) {
          wx.hideLoading();
          const errMsg = (typeof e === 'string' && e) ? e : (e && e.msg) ? e.msg : '抢占名额失败，请重试';
          this.showError(errMsg);
          return;
        }
      }
    } else if (step === 2) {
      // 第三步：基本信息
      const fields = { xm: '姓名', xb: '性别', mz: '民族', zzmm: '政治面貌', hkxz: '户口类型' };
      for (const key in fields) {
        if (!bmxs[key] && bmxs[key] !== 0) {
          this.showError(`请填写${fields[key]}`);
          return;
        }
      }
      if (bmxs.sfjdlk === '' || bmxs.sfjdlk === null || bmxs.sfjdlk === undefined) {
        this.showError('请选择是否建档立卡');
        return;
      }
    } else if (step === 3) {
      // 第四步：家庭信息
      const fields = {
        jtxxdz: '家庭详细地址', byxxmc: '毕业学校名称',
        byxxssx1: '毕业学校所在省', jzxm: '家长姓名', jzgx: '与家长关系',
        jzdlx: '居住地类型', jzdh: '家长电话'
      };
      for (const key in fields) {
        if (!bmxs[key] && bmxs[key] !== 0) {
          this.showError(`请填写${fields[key]}`);
          return;
        }
      }
      if (!bmxs.xsdh) {
        this.showError('学生电话格式不正确');
        return;
      }
      const phoneReg = /^1[3-9]\d{9}$/;
      if (!phoneReg.test(bmxs.xsdh)) {
        this.showError('学生电话格式不正确');
        return;
      }
      if (!phoneReg.test(bmxs.jzdh)) {
        this.showError('家长电话格式不正确');
        return;
      }
    } else if (step === 4) {
      // 第五步：校服
      if (bmxs.sfqdxf === '' || bmxs.sfqdxf === null || bmxs.sfqdxf === undefined) {
        this.showError('请选择是否购买校服');
        return;
      }
      if (bmxs.sfqdxf !== 0 && bmxs.sfqdxf !== 1) {
        this.showError('请选择是否购买校服');
        return;
      }
    } else if (step === 5) {
      // 第六步：招生信息
      const fields = {
        xsly: '招生来源', zsdx: '招生对象', qd: '渠道'
      };
      for (const key in fields) {
        if (!bmxs[key] && bmxs[key] !== 0) {
          this.showError(`请选择${fields[key]}`);
          return;
        }
      }
      if (bmxs.qd == 7 && !bmxs.qdjs) {
        this.showError('请填写渠道介绍人');
        return;
      }
    }

    wx.pageScrollTo({ scrollTop: 0, duration: 200 });
    this.setData({ currentStep: step + 1 });
  },

  // 实时查询某专业的最新剩余名额，返回 remaining（失败返回 null）。
  // 同时把结果回写到 bdzyArray[1]、tempSchoolList、顶层 remaining，
  // 让"已选择专业卡片"和选择器列表都实时显示最新名额。
  async fetchLatestRemaining(majorId) {
    if (!majorId) return null;
    try {
      const result = await get('/zzbm/get_remaining_spots', { major_id: majorId }, { showLoading: false });
      const remaining = (result && result.remaining !== undefined) ? result.remaining : null;
      if (remaining === null) return null;

      const updatePayload = { remaining };

      // 整体替换 bdzyArray[1]：定位 majorId，克隆数组替换对应项的 remaining
      const bdzyList = (this.data.bdzyArray && this.data.bdzyArray[1]) ? this.data.bdzyArray[1] : [];
      const bdzyIdx = bdzyList.findIndex(it => it && it.id === majorId);
      if (bdzyIdx >= 0) {
        const newBdzyList = bdzyList.slice();
        newBdzyList[bdzyIdx] = Object.assign({}, newBdzyList[bdzyIdx], { remaining });
        updatePayload.bdzyArray = [this.data.bdzyArray[0], newBdzyList];
      }

      // 整体替换 tempSchoolList（picker 弹层使用）
      const tempList = this.data.tempSchoolList || [];
      const tempIdx = tempList.findIndex(it => it && it.id === majorId);
      if (tempIdx >= 0) {
        const newTempList = tempList.slice();
        newTempList[tempIdx] = Object.assign({}, newTempList[tempIdx], { remaining });
        updatePayload.tempSchoolList = newTempList;
      }

      console.log('[fetchLatestRemaining] 更新名额', { majorId, remaining, bdzyIdx, tempIdx });
      // 同步更新 majorRemainingMap（供 _buildSchoolList 使用）
      updatePayload.majorRemainingMap = Object.assign({}, this.data.majorRemainingMap || {}, { [majorId]: remaining });
      this.setData(updatePayload);
      return remaining;
    } catch (e) {
      console.warn('查询最新名额失败', e);
      return null;
    }
  },

  // 实时刷新所选专业的剩余名额（每次切换到第4步时调用）
  async refreshRemainingSpots() {
    const bdzyArray = this.data.bdzyArray;
    const bdzyIndex = this.data.bdzyIndex;
    if (!bdzyIndex || bdzyIndex.length < 2 || !bdzyArray[1] || !bdzyArray[1][bdzyIndex[1]]) return;

    const majorId = bdzyArray[1][bdzyIndex[1]].id;
    if (!majorId) return;

    try {
      // get() 已解包 responseData.data，result 直接是 {major_id, zsme, actual_count, remaining}
      const result = await get('/zzbm/get_remaining_spots', { major_id: majorId }, { showLoading: false });
      if (result && result.remaining !== undefined) {
        const key = `bdzyArray[1][${bdzyIndex[1]}].remaining`;
        this.setData({
          [key]: result.remaining,
          remaining: result.remaining  // 同步顶层字段，确保 onSubmit 检查正确
        });
      }
    } catch (e) {
      console.warn('刷新剩余名额失败', e);
    }
  },

  // 更新报名记录的专业（专业变更时调用）
  async updateEnrollmentMajor(newBdzy) {
    if (!this.data.enrollmentId) return;
    try {
      const result = await post('/zzbm/update_info', {
        id: this.data.enrollmentId,
        bdzy: newBdzy
      }, { loadingTitle: '更新专业中...' });
      if (result && result.success === false) {
        wx.showModal({
          title: '专业变更失败',
          content: result.msg || '请重试',
          showCancel: false,
          confirmText: '我知道了'
        });
      }
    } catch (e) {
      console.error('更新专业失败', e);
    }
  },

  // 上一步
  prevStep() {
    if (this.data.currentStep > 0) {
      wx.pageScrollTo({ scrollTop: 0, duration: 200 });
      this.setData({ currentStep: this.data.currentStep - 1 });
    }
  },

  getObjNameToArray(objArray) {
    if (!Array.isArray(objArray)) return [];
    return objArray.map(item => item.name);
  },

  // 获取报名信息
  async getBmxsInfo() {
    try {
      const result = await get('/zzbm/get_new_zzbm_info',{},{loadingTitle: '获取报名专业信息中...'});

      // 防御性检查：确保返回数据结构完整
      if (!result || !result.options) {
        console.error('获取报名信息：返回数据结构异常', result);
        this.showError('报名数据加载失败，请稍后重试');
        return;
      }

      const options = result.options;
      // bdzy_list 延迟到进入第二步时由 loadBdzyList() 加载，避免一开始就拿到陈旧的剩余名额

      // 一次性合并所有 setData，避免外部 await getBmxsInfo() 后读 this.data.* 仍是旧值
      const dataPatch = {};
      if (options.zzmm && Array.isArray(options.zzmm)) {
        dataPatch.zzmmArray = options.zzmm.map(it => it.name);
        dataPatch.zzmmIdArray = options.zzmm.map(it => it.id);
      }
      if (options.jzgx && Array.isArray(options.jzgx)) {
        dataPatch.jzgxArray = options.jzgx.map(it => it.name);
        dataPatch.jzgxIdArray = options.jzgx.map(it => it.id);
      }
      if (options.jzdlx && Array.isArray(options.jzdlx)) {
        dataPatch.jzdlxArray = options.jzdlx.map(it => it.name);
        dataPatch.jzdlxIdArray = options.jzdlx.map(it => it.id);
      }
      if (options.zsdx && Array.isArray(options.zsdx)) {
        dataPatch.zsdxArray = options.zsdx.map(it => it.name);
        dataPatch.zsdxIdArray = options.zsdx.map(it => it.id);
      }
      if (options.qd && Array.isArray(options.qd)) {
        dataPatch.qdArray = options.qd.map(it => it.name);
        dataPatch.qdIdArray = options.qd.map(it => it.id);
      }
      // 一次性 setData 并 await 完成回调，确保调用方在 await getBmxsInfo() 后 this.data.* 已更新
      await new Promise(resolve => this.setData(dataPatch, resolve));

    } catch (error) {
      console.error('获取报名信息失败：', error);
    }
  },

  // 加载报考学校及专业列表（进入第二步时调用，时机最贴近"用户选专业"那一刻）
  async loadBdzyList() {
    try {
      const result = await get('/zzbm/get_new_zzbm_info', {}, { loadingTitle: '获取报考专业中...' });
      if (!result || !result.options || !result.options.bdzy_list) {
        console.error('loadBdzyList: 返回数据异常', result);
        wx.showToast({ title: '专业数据加载失败', icon: 'none' });
        return false;
      }
      const bdzyList = result.options.bdzy_list;
      console.log('[loadBdzyList] result:', JSON.stringify(result).substring(0, 200));
      console.log('[loadBdzyList] bdzyList length:', bdzyList ? bdzyList.length : 'null/undefined');
      const bdzyNames = bdzyList.map(bdzy => ({ id: String(bdzy.id), name: bdzy.major_name }));

      // 编辑模式：找到当前专业所在的类别，用该类别填充 bdzyArray[1]
      // 否则默认用第 0 类
      const studentBdzy = this.data.bmxs && this.data.bmxs.bdzy;
      console.log('[loadBdzyList] studentBdzy:', studentBdzy, typeof studentBdzy);
      let activeCatIdx = (this.data.bdzyIndex && this.data.bdzyIndex.length > 0) ? this.data.bdzyIndex[0] : 0;
      if (studentBdzy) {
        const foundCat = bdzyList.findIndex(cat =>
          (cat.cooperation_schoolmajors || []).some(sm => String(sm.school_major_name_id) === String(studentBdzy))
        );
        console.log('[loadBdzyList] foundCat index:', foundCat);
        if (foundCat >= 0) activeCatIdx = foundCat;
      }
      const activeCat = bdzyList[activeCatIdx] || bdzyList[0];
      const initialSchoolmajorList = (activeCat && activeCat.cooperation_schoolmajors)
        ? activeCat.cooperation_schoolmajors.map(schoolmajor => ({
            id: String(schoolmajor.school_major_name_id),
            name: (schoolmajor.zsme - schoolmajor.bmrs) + '_' + schoolmajor.cooperation_major + '\n' + schoolmajor.cooperation_school,
            cooperation_school: schoolmajor.cooperation_school,
            cooperation_major: schoolmajor.cooperation_major,
            remaining: schoolmajor.zsme - schoolmajor.bmrs,
            remark: schoolmajor.remark
          }))
        : [];
      this.setData({
        bdzys: bdzyList,
        bdzyArray: [bdzyNames, initialSchoolmajorList],
        bdzyIndex: []   // 临时清空，由调用方在适当时机恢复
      });

      // 收集所有专业 id（所有类别）
      const allMajors = [];
      bdzyList.forEach(cat => {
        (cat.cooperation_schoolmajors || []).forEach(sm => {
          if (sm.school_major_name_id) allMajors.push(sm.school_major_name_id);
        });
      });

      // 一次拉一个专业的最新名额（按 5 并发），记录到 remainingMap
      const remainingMap = {};
      const concurrency = 5;
      for (let i = 0; i < allMajors.length; i += concurrency) {
        const chunk = allMajors.slice(i, i + concurrency);
        await Promise.all(chunk.map(async (majorId) => {
          try {
            const r = await get('/zzbm/get_remaining_spots', { major_id: majorId }, { showLoading: false });
            if (r && r.remaining !== undefined) {
              remainingMap[majorId] = r.remaining;
            }
          } catch (e) {
            // 单个失败忽略
          }
        }));
      }

      // 把实时名额存到 data（供 _buildSchoolList 使用），不污染 bdzys 原始字段
      const newDefaultList = (initialSchoolmajorList || []).map(item => {
        if (item && item.id !== undefined && remainingMap[item.id] !== undefined) {
          return Object.assign({}, item, { remaining: remainingMap[item.id] });
        }
        return item;
      });
      this.setData({
        majorRemainingMap: remainingMap,
        bdzyArray: [bdzyNames, newDefaultList]
      });
      return true;
    } catch (e) {
      console.error('loadBdzyList 失败', e);
      wx.showToast({ title: '专业数据加载失败', icon: 'none' });
      return false;
    }
  },
  // 加载本地存储的表单数据
  loadFormData() {
    try {
      const savedData = wx.getStorageSync('vocational_zzbm_form')
      if (savedData) {
        const data = JSON.parse(savedData)
        // 恢复表单数据
        this.setData({
          bmxs: data.bmxs || { ...this.data.bmxs, bdzy: null },
          xbIndex: data.xbIndex,
          mzIndex: data.mzIndex,
          zzmmIndex: data.zzmmIndex,
          hkxzIndex: data.hkxzIndex,
          sfjdlkIndex: data.sfjdlkIndex,
          sflsetIndex: data.sflsetIndex,
          jzgxIndex: data.jzgxIndex,
          jzdlxIndex: data.jzdlxIndex,
          zsdxIndex: data.zsdxIndex,
          qdIndex: data.qdIndex,
          zslyIndex: data.zslyIndex,
          sfqdxfIndex: data.sfqdxfIndex,
          bdzyIndex: data.bdzyIndex || [],
          address: data.address || this.data.address,
          enrollmentId: data.enrollmentId || null
        })
      }
    } catch (error) {
      console.error('加载本地数据失败：', error)
    }
  },

  // 保存表单数据到本地存储
  saveFormData() {
    try {
      const data = {
        bmxs: this.data.bmxs,
        xbIndex: this.data.xbIndex,
        mzIndex: this.data.mzIndex,
        zzmmIndex: this.data.zzmmIndex,
        hkxzIndex: this.data.hkxzIndex,
        sfjdlkIndex: this.data.sfjdlkIndex,
        sflsetIndex: this.data.sflsetIndex,
        jzgxIndex: this.data.jzgxIndex,
        jzdlxIndex: this.data.jzdlxIndex,
        zsdxIndex: this.data.zsdxIndex,
        qdIndex: this.data.qdIndex,
        zslyIndex: this.data.zslyIndex,
        sfqdxfIndex: this.data.sfqdxfIndex,
        bdzyIndex: this.data.bdzyIndex,
        address: this.data.address,
        enrollmentId: this.data.enrollmentId
      }
      wx.setStorageSync('vocational_zzbm_form', JSON.stringify(data))
    } catch (error) {
      console.error('保存本地数据失败：', error)
    }
  },

  // 清空表单数据
  clearFormData() {
    wx.showModal({
      title: '提示',
      content: '确定要清空所有已填写的信息吗？',
      success: (res) => {
        if (res.confirm) {
          // 清空本地存储
          wx.removeStorageSync('vocational_zzbm_form')
          // 重置表单数据
          this.setData({
            bmxs: {
              bdzy: null,
              byxxmc: "",
              byxxssx1: "",
              byxxssx2: "",
              byxxssx3: "",
              hkxz: "",
              id: null,
              jtxxdz: "",
              jzdh: "",
              jzdlx: null,
              jzgx: "",
              jzxm: "",
              mz: "",
              pc: null,
              qd: null,
              qdjs: "",
              sfjdlk: "",
              sflset: 0,
              sftwjrzn: 0,
              sfqdxf: null,
              sfzh: "",
              tjsj: null,
              xb: "",
              xm: "",
              xsdh: "",
              xsly: "",
              zsdx: null,
              zzmm: null
            },
            xbIndex: null,
            mzIndex: null,
            zzmmIndex: null,
            hkxzIndex: null,
            sfjdlkIndex: null,
            sflsetIndex: null,
            jzgxIndex: null,
            jzdlxIndex: null,
            zsdxIndex: null,
            qdIndex: null,
            zslyIndex: null,
            sfqdxfIndex: null,
            bdzyIndex: [0, 0],
            address: ['贵州省','黔东南苗族侗族自治州','凯里市'],
            enrollmentId: null
          })
          wx.showToast({
            title: '已清空',
            icon: 'success'
          })
        }
      }
    })
  },

  // 表单项变化
  onFieldChange(e) {
    const name = e.currentTarget.dataset.name
    const value = e.detail
    this.setData({
      [`bmxs.${name}`]: value
    }, () => {
      this.saveFormData()
    })
  },

  // 报名完成开关变化处理
  onIsCompleteChange(e) {
    this.setData({
      'bmxs.is_complete': e.detail ? 1 : 0
    }, () => {
      this.saveFormData()
    })
  },

// --------------------------------------------------------------------======================
  // ---- 专业选择自定义弹出层方法 ----
  openMajorPicker() {
    if (!this.data.bdzys || this.data.bdzys.length === 0) {
      this.showError('专业数据未加载，请稍候重试');
      return;
    }
    const catIdx = (this.data.bdzyIndex && this.data.bdzyIndex.length > 0) ? this.data.bdzyIndex[0] : 0;
    // 先用本地数据填充（同上次的关闭状态保留），再异步拉一次最新名额覆盖，避免 picker 显示陈旧值
    const initialList = this._buildSchoolList(catIdx);
    this.setData({
      showMajorPickerPopup: true,
      tempCatIndex: catIdx,
      tempSchoolList: initialList
    });

    // 异步刷新当前大类的所有专业实时名额
    const currentMajors = (this.data.bdzys[catIdx] && this.data.bdzys[catIdx].cooperation_schoolmajors)
      ? this.data.bdzys[catIdx].cooperation_schoolmajors.map(sm => sm.school_major_name_id).filter(Boolean)
      : [];
    // 并发 5 拉取
    const concurrency = 5;
    (async () => {
      const remainingMap = this.data.majorRemainingMap || {};
      for (let i = 0; i < currentMajors.length; i += concurrency) {
        const chunk = currentMajors.slice(i, i + concurrency);
        await Promise.all(chunk.map(async (majorId) => {
          try {
            const r = await get('/zzbm/get_remaining_spots', { major_id: majorId }, { showLoading: false });
            if (r && r.remaining !== undefined) {
              remainingMap[majorId] = r.remaining;
            }
          } catch (e) { /* ignore */ }
        }));
      }
      // 合并到全局 remainingMap，然后重建当前类别的 tempSchoolList
      const updatedList = this._buildSchoolList(catIdx);
      this.setData({
        majorRemainingMap: remainingMap,
        tempSchoolList: updatedList
      });
    })();
  },

  closeMajorPicker() {
    this.setData({ showMajorPickerPopup: false });
  },

  onMajorCatTap(e) {
    const idx = e.currentTarget.dataset.index;
    // 先填充，再用异步获取的最新名额覆盖
    const initialList = this._buildSchoolList(idx);
    this.setData({
      tempCatIndex: idx,
      tempSchoolList: initialList
    });

    // 异步刷新该类别的所有专业实时名额
    const currentMajors = (this.data.bdzys[idx] && this.data.bdzys[idx].cooperation_schoolmajors)
      ? this.data.bdzys[idx].cooperation_schoolmajors.map(sm => sm.school_major_name_id).filter(Boolean)
      : [];
    const concurrency = 5;
    (async () => {
      const remainingMap = this.data.majorRemainingMap || {};
      for (let i = 0; i < currentMajors.length; i += concurrency) {
        const chunk = currentMajors.slice(i, i + concurrency);
        await Promise.all(chunk.map(async (majorId) => {
          try {
            const r = await get('/zzbm/get_remaining_spots', { major_id: majorId }, { showLoading: false });
            if (r && r.remaining !== undefined) {
              remainingMap[majorId] = r.remaining;
            }
          } catch (e) { /* ignore */ }
        }));
      }
      const updatedList = this._buildSchoolList(idx);
      this.setData({
        majorRemainingMap: remainingMap,
        tempSchoolList: updatedList
      });
    })();
  },

  onMajorItemTap(e) {
    const catIdx = this.data.tempCatIndex;
    const itemIdx = e.currentTarget.dataset.index;
    const item = this.data.tempSchoolList[itemIdx];
    if (!item) return;
    const schoolmajorList = this._buildSchoolList(catIdx);

    const oldBdzy = String(this.data.bmxs.bdzy || '');
    const newBdzy = String(item.id);

    // 编辑模式下禁止选择已经报名的同一专业
    if (this.data.isEditMode && this.data.originalBdzy && String(this.data.originalBdzy) === newBdzy) {
      wx.showToast({ title: '该专业已是您当前报名专业', icon: 'none' });
      return;
    }

    this.setData({
      'bmxs.bdzy': String(item.id),
      bdzyIndex: [catIdx, itemIdx],
      'bdzyArray[1]': schoolmajorList,
      remaining: item.remaining,
      showMajorPickerPopup: false
    }, () => {
      this.fetchLatestRemaining(item.id);
      wx.showToast({ title: '已选择专业', icon: 'success' });

      if (this.data.isEditMode) {
        // 编辑模式：仅本地更新，专业变更等用户点击"下一步"时由 nextStep 统一提交到后端
        this.saveFormData();
      }
      // 新报名模式：此时只存本地，等 step 1 → step 2 提交时再抢占名额
    });
  },

  _buildSchoolList(catIdx) {
    const bdzys = this.data.bdzys;
    if (!bdzys || !bdzys[catIdx]) return [];
    const remainingMap = this.data.majorRemainingMap || {};
    return bdzys[catIdx].cooperation_schoolmajors.map(sm => {
      // 优先用 loadBdzyList 拉取的实时名额；否则退回 sm.zsme - sm.bmrs
      const liveRemaining = remainingMap[sm.school_major_name_id];
      const remaining = (liveRemaining !== undefined)
        ? liveRemaining
        : (sm.zsme - sm.bmrs);
      return {
        id: sm.school_major_name_id,
        cooperation_school: sm.cooperation_school,
        cooperation_major: sm.cooperation_major,
        remaining,
        remark: sm.remark
      };
    });
  },

  // 报考学校及专业列改变事件，在用户选择时的联动处理
  bdzyPickerColumnChange: function(e) {
    const { column, value } = e.detail;
    switch (column) {
      case 0:
          const selectedMajorIndex = value;
          const selectedMajor = this.data.bdzys[selectedMajorIndex]
          const schoolmajorList = selectedMajor.cooperation_schoolmajors.map(schoolmajor => ({
            id: String(schoolmajor.school_major_name_id),
            name:(schoolmajor.zsme - schoolmajor.bmrs)+'_'+schoolmajor.cooperation_major+'_'+schoolmajor.cooperation_school,
            cooperation_school:schoolmajor.cooperation_school,
            cooperation_major:schoolmajor.cooperation_major,
            remaining:schoolmajor.zsme - schoolmajor.bmrs,
            remark:schoolmajor.remark
          }));
          this.setData({
            'bdzyArray[1]': schoolmajorList,
            'bdzyIndex[0]': selectedMajorIndex,
            'bdzyIndex[1]': 0 // 重置第二列的选择为第一个
          });
    }
  },

  // 报考学校及专业改变事件,处理选择完成以后的处理
  bdzyPickerChange: function(e) {
    // 如果bdzyIndex是空数组或未定义,将其初始化为[0, 0]
    if (!this.data.bdzyIndex || this.data.bdzyIndex.length === 0) {
      this.setData({
        bdzyIndex: [0, 0]
      });
    }


    // 获取选择的专业信息
    const selectedMajor = this.data.bdzyArray[1][e.detail.value[1]];
    const oldBdzy = String(this.data.bmxs.bdzy || '');
    const newBdzy = String(this.data.bdzyArray[1][e.detail.value[1]].id);

    this.setData({
      'bmxs.bdzy': String(this.data.bdzyArray[1][e.detail.value[1]].id),
      'bdzyIndex[0]': e.detail.value[0],
      'bdzyIndex[1]': e.detail.value[1],
      'remaining': selectedMajor.remaining
    }, () => {
      this.saveFormData();

      // 拉一次最新名额，回写到列表和顶层，避免停留期间名额已变但 UI 还显示有名额
      this.fetchLatestRemaining(newBdzy);

      // 如果已预创建报名记录且专业变更，需要更新后端
      if (this.data.enrollmentId && oldBdzy && oldBdzy !== newBdzy) {
        this.updateEnrollmentMajor(newBdzy);
      }
    })
  },

  
  // 开始换新的选择器了，从这里开始----------------------------------------------------


  // 性别改变事件
  xbPickerChange: function(e) {
    this.setData({
      xbIndex: e.detail.value,
      'bmxs.xb': this.data.xbArray[e.detail.value]
    }, () => {
      this.saveFormData()
    })
  },

  // 民族改变事件
  mzPickerChange: function(e) {
    this.setData({
      mzIndex: e.detail.value,
      'bmxs.mz': this.data.mzArray[e.detail.value]
    }, () => {
      this.saveFormData()
    })
  },
  // 政治面貌改变事件
  zzmmPickerChange: function(e) {
    const idx = e.detail.value;
    const id = (this.data.zzmmIdArray && this.data.zzmmIdArray[idx] !== undefined)
      ? this.data.zzmmIdArray[idx]
      : null;
    this.setData({
      zzmmIndex: idx,
      'bmxs.zzmm': id
    }, () => {
      this.saveFormData()
    })
  },


  
  // 是否建档立卡改变事件
  sfjdlkPickerChange: function(e) {
    this.setData({
      sfjdlkIndex: e.detail.value,
      'bmxs.sfjdlk': parseInt(e.detail.value)
    }, () => {
      this.saveFormData()
    })
  },

  // 是否留守儿童改变事件
  sflsetPickerChange: function(e) {
    this.setData({
      sflsetIndex: e.detail.value,
      'bmxs.sflset': parseInt(e.detail.value)
    }, () => {
      this.saveFormData()
    })
  },


  // 户口类型改变事件
  hkxzPickerChange: function(e) {
    this.setData({
      hkxzIndex: e.detail.value,
      'bmxs.hkxz': this.data.hkxzArray[e.detail.value]
    }, () => {
      this.saveFormData()
    })
  },
  

  // 与家长关系改变事件
  jzgxPickerChange: function(e) {
    const idx = e.detail.value;
    const id = (this.data.jzgxIdArray && this.data.jzgxIdArray[idx] !== undefined)
      ? this.data.jzgxIdArray[idx]
      : null;
    this.setData({
      jzgxIndex: idx,
      'bmxs.jzgx': id
    }, () => {
      this.saveFormData()
    })
  },

  // 居住地类型改变事件
  jzdlxPickerChange: function(e) {
    const idx = e.detail.value;
    const id = (this.data.jzdlxIdArray && this.data.jzdlxIdArray[idx] !== undefined)
      ? this.data.jzdlxIdArray[idx]
      : null;
    this.setData({
      jzdlxIndex: idx,
      'bmxs.jzdlx': id
    }, () => {
      this.saveFormData()
    })
  },


  // 招生对象改变事件
  zsdxPickerChange: function(e) {
    const idx = e.detail.value;
    const id = (this.data.zsdxIdArray && this.data.zsdxIdArray[idx] !== undefined)
      ? this.data.zsdxIdArray[idx]
      : null;
    this.setData({
      zsdxIndex: idx,
      'bmxs.zsdx': id
    }, () => {
      this.saveFormData()
    })
  },


  // 渠道改变事件
  qdPickerChange: function(e) {
    const idx = e.detail.value;
    const id = (this.data.qdIdArray && this.data.qdIdArray[idx] !== undefined)
      ? this.data.qdIdArray[idx]
      : null;
    this.setData({
      qdIndex: idx,
      'bmxs.qd': id
    }, () => {
      this.saveFormData()
    })
  },


  // 地区选择器联动
  regonPickerChange(picker) {
    this.setData({
      'address': picker.detail.value,
      'bmxs.byxxssx1': picker.detail.value[0],
      'bmxs.byxxssx2': picker.detail.value[1], 
      'bmxs.byxxssx3': picker.detail.value[2]
    }, () => {
      this.saveFormData()
    })    
  },

  // 招生来源改变事件
  zslyPickerChange: function(e) {
    this.setData({
      zslyIndex: e.detail.value,
      'bmxs.xsly': this.data.zslyArray[e.detail.value]
    }, () => {
      this.saveFormData()
    })
  },

  // 是否购买校服改变事件
  sfqdxfPickerChange: function(e) {
    this.setData({
      sfqdxfIndex: e.detail.value,
      'bmxs.sfqdxf': parseInt(e.detail.value)
    }, () => {
      this.saveFormData()
    })
  },

  // ==================== 提交表单 ====================

  goToPayment() {
    const sfzh = this.data.bmxs.sfzh;
    if (sfzh) {
      wx.navigateTo({
        url: '/packageVocational/pages/vocational-new-payment/vocational-new-payment?idNumber=' + sfzh
      });
    }
  },

  // 同步picker索引到对应的数据
  _syncPickerIndexes(record) {
    // 性别
    const xbArr = this.data.xbArray || [];
    const xbIdx = xbArr.indexOf(record.xb);
    if (xbIdx >= 0) this.setData({ xbIndex: xbIdx });

    // 民族
    const mzArr = this.data.mzArray || [];
    const mzIdx = mzArr.indexOf(record.mz);
    if (mzIdx >= 0) this.setData({ mzIndex: mzIdx });

    // 户口
    const hkArr = this.data.hkxzArray || [];
    const hkIdx = hkArr.indexOf(record.hkxz);
    if (hkIdx >= 0) this.setData({ hkxzIndex: hkIdx });

    // 地区
    if (record.byxxssx1) {
      this.setData({ address: [record.byxxssx1, record.byxxssx2 || '', record.byxxssx3 || ''] });
    }

    // 政治面貌 - 后端存数据库 ID，按 id 找索引
    if (record.zzmm !== undefined && record.zzmm !== null && record.zzmm !== '') {
      const zzmmIdArr = this.data.zzmmIdArray || [];
      const target = (typeof record.zzmm === 'string') ? record.zzmm : String(record.zzmm);
      let zzmmIdx = zzmmIdArr.indexOf(target);
      if (zzmmIdx < 0) zzmmIdx = zzmmIdArr.indexOf(parseInt(record.zzmm));
      if (zzmmIdx < 0) zzmmIdx = parseInt(record.zzmm) - 1;
      if (zzmmIdx >= 0) this.setData({ zzmmIndex: zzmmIdx });
    }

    // 是否建档立卡 - 后端存 0-1 对应数组索引 0-1
    if (record.sfjdlk !== undefined && record.sfjdlk !== null && record.sfjdlk !== '') {
      const sfjdlkIdx = parseInt(record.sfjdlk);
      if (sfjdlkIdx >= 0) this.setData({ sfjdlkIndex: sfjdlkIdx });
    }

    // 是否留守儿童 - 后端存 0-1 对应数组索引 0-1
    if (record.sflset !== undefined && record.sflset !== null && record.sflset !== '') {
      const sflsetIdx = parseInt(record.sflset);
      if (sflsetIdx >= 0) this.setData({ sflsetIndex: sflsetIdx });
    }

    // 与家长关系 - 后端存数据库 ID，按 id 找索引
    if (record.jzgx !== undefined && record.jzgx !== null && record.jzgx !== '') {
      const jzgxIdArr = this.data.jzgxIdArray || [];
      const target = (typeof record.jzgx === 'string') ? record.jzgx : String(record.jzgx);
      let jzgxIdx = jzgxIdArr.indexOf(target);
      if (jzgxIdx < 0) jzgxIdx = jzgxIdArr.indexOf(parseInt(record.jzgx));
      if (jzgxIdx < 0) jzgxIdx = parseInt(record.jzgx) - 1;
      if (jzgxIdx >= 0) {
        this.setData({ jzgxIndex: jzgxIdx });
      }
    }

    // 居住地类型 - 后端存数据库 ID，按 id 找索引
    if (record.jzdlx !== undefined && record.jzdlx !== null && record.jzdlx !== '') {
      const jzdlxIdArr = this.data.jzdlxIdArray || [];
      const target = (typeof record.jzdlx === 'string') ? record.jzdlx : String(record.jzdlx);
      let jzdlxIdx = jzdlxIdArr.indexOf(target);
      if (jzdlxIdx < 0) jzdlxIdx = jzdlxIdArr.indexOf(parseInt(record.jzdlx));
      if (jzdlxIdx < 0) jzdlxIdx = parseInt(record.jzdlx) - 1;
      if (jzdlxIdx >= 0) {
        this.setData({ jzdlxIndex: jzdlxIdx });
      }
    }

    // 招生来源 - 字符串匹配
    const zslyArr = this.data.zslyArray || [];
    const zslyIdx = zslyArr.indexOf(record.xsly);
    if (zslyIdx >= 0) this.setData({ zslyIndex: zslyIdx });

    // 招生对象 - 后端存数据库 ID，按 id 找索引
    if (record.zsdx !== undefined && record.zsdx !== null && record.zsdx !== '') {
      const zsdxIdArr = this.data.zsdxIdArray || [];
      const target = (typeof record.zsdx === 'string') ? record.zsdx : String(record.zsdx);
      let zsdxIdx = zsdxIdArr.indexOf(target);
      if (zsdxIdx < 0) zsdxIdx = zsdxIdArr.indexOf(parseInt(record.zsdx));
      if (zsdxIdx < 0) zsdxIdx = parseInt(record.zsdx) - 1;
      if (zsdxIdx >= 0) {
        this.setData({ zsdxIndex: zsdxIdx });
      }
    }

    // 渠道 - 后端存数据库 ID，按 id 找索引
    if (record.qd !== undefined && record.qd !== null && record.qd !== '') {
      const qdIdArr = this.data.qdIdArray || [];
      const target = (typeof record.qd === 'string') ? record.qd : String(record.qd);
      let qdIdx = qdIdArr.indexOf(target);
      if (qdIdx < 0) qdIdx = qdIdArr.indexOf(parseInt(record.qd));
      if (qdIdx < 0) qdIdx = parseInt(record.qd) - 1;
      if (qdIdx >= 0) {
        this.setData({ qdIndex: qdIdx });
      }
    }

    // 是否购买校服 - 后端存 0-1 对应数组索引 0-1
    if (record.sfqdxf !== undefined && record.sfqdxf !== null && record.sfqdxf !== '') {
      const sfqdxfIdx = parseInt(record.sfqdxf);
      if (sfqdxfIdx >= 0) {
        this.setData({ sfqdxfIndex: sfqdxfIdx });
      }
    }

    // 专业 — 从 bdzys 原始数据中找到对应的 category 和 item
    const bdzys = this.data.bdzys;
    if (bdzys && record.bdzy) {
      const bdzyIdStr = String(record.bdzy);
      for (let catIdx = 0; catIdx < bdzys.length; catIdx++) {
        const cat = bdzys[catIdx];
        if (!cat.cooperation_schoolmajors) continue;
        for (let itemIdx = 0; itemIdx < cat.cooperation_schoolmajors.length; itemIdx++) {
          const sm = cat.cooperation_schoolmajors[itemIdx];
          if (String(sm.school_major_name_id) === bdzyIdStr) {
            // 找到了！构建 schoolList 并设置索引
            const schoolmajorList = this._buildSchoolList(catIdx);
            this.setData({
              bdzyIndex: [catIdx, itemIdx],
              'bdzyArray[1]': schoolmajorList,
              remaining: sm.zsme - sm.bmrs,
              tempCatIndex: catIdx,
              tempSchoolList: schoolmajorList
            });

            // 编辑模式回填后，异步拉一次当前选中专业的最新名额，更新 bdzyArray 和 tempSchoolList
            (async () => {
              const r = await get('/zzbm/get_remaining_spots', { major_id: sm.school_major_name_id }, { showLoading: false });
              if (r && r.remaining !== undefined) {
                const newBdzyList = (this.data.bdzyArray[1] || []).map(it => String(it.id) === bdzyIdStr ? Object.assign({}, it, { remaining: r.remaining }) : it);
                const newTempList = (this.data.tempSchoolList || []).map(it => String(it.id) === bdzyIdStr ? Object.assign({}, it, { remaining: r.remaining }) : it);
                const remainingMap = Object.assign({}, this.data.majorRemainingMap || {}, { [bdzyIdStr]: r.remaining });
                this.setData({
                  bdzyArray: [this.data.bdzyArray[0], newBdzyList],
                  tempSchoolList: newTempList,
                  majorRemainingMap: remainingMap,
                  remaining: r.remaining
                });
              }
            })();

            return;
          }
        }
      }
    }
  },

  // 同步专业索引（编辑模式加载后调用）
  _syncMajorIndex(bdzyId) {
    const bdzys = this.data.bdzys;
    if (!bdzys || !bdzyId) return;
    const bdzyIdStr = String(bdzyId);
    for (let catIdx = 0; catIdx < bdzys.length; catIdx++) {
      const cat = bdzys[catIdx];
      if (!cat.cooperation_schoolmajors) continue;
      for (let itemIdx = 0; itemIdx < cat.cooperation_schoolmajors.length; itemIdx++) {
        const sm = cat.cooperation_schoolmajors[itemIdx];
        if (String(sm.school_major_name_id) === bdzyIdStr) {
          const schoolmajorList = this._buildSchoolList(catIdx);
          this.setData({
            bdzyIndex: [catIdx, itemIdx],
            'bdzyArray[1]': schoolmajorList,
            tempCatIndex: catIdx,
            tempSchoolList: schoolmajorList
          });
          return;
        }
      }
    }
  },

  // 已报名时：加载详情，进入编辑模式，并跳到 step 1
  async _loadEnrolledAndEnterStep1() {
    try {
      wx.showLoading({ title: '加载报名信息...' });
      // 先确保字典数组已加载（zzmm/jzdlx 等 id 数组），否则后续 _syncPickerIndexes 无法反查索引
      await this.getBmxsInfo();
      const loadRes = await get('/zzbm/get_enrollment_detail_by_sfzh', {
        sfzh: this.data.bmxs.sfzh.toUpperCase(),
        verify_token: this.data.verifyToken || ''
      }, { showLoading: false });
      wx.hideLoading();
      if (!loadRes || !loadRes.record) {
        this.showError('已报名但无法加载信息，请联系管理员');
        return;
      }
      const record = loadRes.record;
      const paymentInfo = loadRes.payment_info || null;
      this.setData({
        isEditMode: true,
        editRecordId: record.id,
        editQueryCode: record.query_code || '',
        paymentInfo: paymentInfo,
        'bmxs.xm': record.xm || '',
        'bmxs.xb': record.xb || '',
        'bmxs.mz': record.mz || '',
        'bmxs.zzmm': record.zzmm,
        'bmxs.sfzh': record.sfzh || '',
        'bmxs.xsdh': record.xsdh || '',
        'bmxs.jtxxdz': record.jtxxdz || '',
        'bmxs.jzdlx': record.jzdlx,
        'bmxs.hkxz': record.hkxz || '',
        'bmxs.jzxm': record.jzxm || '',
        'bmxs.jzgx': record.jzgx,
        'bmxs.jzdh': record.jzdh || '',
        'bmxs.bdzy': String(record.bdzy),
        'bmxs.byxxssx1': record.byxxssx1 || '',
        'bmxs.byxxssx2': record.byxxssx2 || '',
        'bmxs.byxxssx3': record.byxxssx3 || '',
        'bmxs.byxxmc': record.byxxmc || '',
        'bmxs.zsdx': record.zsdx,
        'bmxs.sfjdlk': record.sfjdlk,
        'bmxs.sflset': record.sflset,
        'bmxs.sftwjrzn': record.sftwjrzn,
        'bmxs.xsly': record.xsly || '',
        'bmxs.qd': record.qd,
        'bmxs.qdjs': record.qdjs || '',
        'bmxs.sfqdxf': record.sfqdxf,
        'bmxs.remark': record.remark || '',
        'bmxs.is_complete': record.is_complete,
        originalBdzy: record.bdzy,
        enrollmentId: record.id,
      });
      this._syncPickerIndexes(record);
      const loaded = await this.loadBdzyList();
      if (!loaded) {
        this.showError('专业数据加载失败');
        return;
      }
      this._syncMajorIndex(record.bdzy);
      wx.showToast({ title: '已加载您的报名记录（编辑模式）', icon: 'success' });
      this.saveFormData();
      this.setData({ currentStep: 1 });
      // 保持停留在当前页（专业选择页），用户自行决定下一步操作
    } catch (loadErr) {
      wx.hideLoading();
      this.showError('加载报名信息失败，请稍后重试');
    }
  },

  // ==================== 已报名用户身份二次验证（手机号快捷认证） ====================

  // 弹窗：要求已报名用户用微信绑定的手机号做快捷身份认证
  // 通过 Promise 在弹窗关闭后返回；验证成功：resolve(true)；用户取消：resolve(false)
  _requireEnrollmentVerifyCode() {
    return new Promise((resolve) => {
      // 重置弹窗状态
      this.setData({
        showVerifyCodeModal: true,
        verifyRole: '',
        verifyRoleToken: '',
        verifyRoleMaskedPhone: '',
        verifyRoleTypeText: '',
        verifyRolePassed: false,
        verifyRoleVerifying: false,
      });
      // 挂一次性 resolve 到实例上
      this._verifyCodeResolve = resolve;
    });
  },

  // "微信手机号快速验证" 按钮回调
  // 用户点击"本人手机"或"家长手机"按钮后，微信会拉起授权面板，回调到此处
  _onEnrollVerifyByPhone(e) {
    if (this.data.verifyRoleVerifying) return;
    if (!e || !e.detail) {
      this.showError('获取手机号失败，请重试');
      return;
    }
    if (e.detail.errMsg && e.detail.errMsg !== 'getPhoneNumber:ok') {
      // 用户拒授权 / 失败，但按钮可重试，不弹 toast 噪音
      if (e.detail.errMsg.indexOf('deny') >= 0 || e.detail.errMsg.indexOf('cancel') >= 0) {
        return;
      }
      this.showError('获取手机号失败，请重试');
      return;
    }
    const code = e.detail.code;
    if (!code) {
      this.showError('获取手机号失败，请重试');
      return;
    }

    const role = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.role) || 'self';

    this.setData({
      verifyRoleVerifying: true,
      verifyRole: role,
      verifyRoleTypeText: role === 'self' ? '本人手机号' : '家长手机号',
    });

    wx.showLoading({ title: '正在校验身份...' });

    post(
      '/vocational_tuition/verify_phone_for_payment',
      { code, role, openid_code: '' },
      { showLoading: false }
    )
      .then((res) => {
        wx.hideLoading();
        const token = (res && (res.verify_token || res.token)) || '';
        const masked = (res && (res.masked_phone || res.phone)) || '';
        if (!token) {
          this.setData({ verifyRoleVerifying: false });
          this.showError('手机号校验失败，请确认是报名预留的手机号');
          return;
        }
        this.setData({
          verifyRoleVerifying: false,
          verifyRoleToken: token,
          verifyRoleMaskedPhone: masked || (role === 'self' ? '本人手机号' : '家长手机号'),
          verifyRolePassed: true,
        });
      })
      .catch((err) => {
        wx.hideLoading();
        this.setData({ verifyRoleVerifying: false });
        // post 工具失败时直接 reject(msg)
        const errMsg = (typeof err === 'string' && err) || (err && err.msg) || '身份校验失败，请稍后重试';
        this.showError(errMsg);
      });
  },

  // 用户点击"验证并进入"
  _submitEnrollmentVerifyCode() {
    if (!this.data.verifyRolePassed || !this.data.verifyRoleToken) {
      this.showError('请先完成微信手机号验证');
      return;
    }
    const token = this.data.verifyRoleToken;
    this.setData({
      verifyToken: token,
      showVerifyCodeModal: false,
    });
    // 缓存验证结果（按身份证号维度），下次进入 step 0 同号直接复用
    const sfzh = (this.data.bmxs && this.data.bmxs.sfzh || '').toUpperCase();
    if (sfzh) {
      this._writeVerifyCache(sfzh, token, 900);
    }
    wx.showToast({ title: '验证成功', icon: 'success' });
    if (typeof this._verifyCodeResolve === 'function') {
      this._verifyCodeResolve(true);
      this._verifyCodeResolve = null;
    }
  },

  // 关闭快捷认证弹窗（用户取消 → 留在当前步骤）
  _closeVerifyCodeModal() {
    this.setData({
      showVerifyCodeModal: false,
      verifyRolePassed: false,
    });
    if (typeof this._verifyCodeResolve === 'function') {
      this._verifyCodeResolve(false);
      this._verifyCodeResolve = null;
    }
  },

  // 读取已报名身份二次验证的本地缓存（按身份证号匹配）
  // 返回 { sfzh, verifyToken, expireAt } 或 null
  _readVerifyCache(sfzh) {
    try {
      if (!sfzh) return null;
      const raw = wx.getStorageSync('vocational_zzbm_verify_cache');
      if (!raw) return null;
      const cache = JSON.parse(raw);
      if (!cache || cache.sfzh !== sfzh || !cache.verifyToken) return null;
      if (cache.expireAt && cache.expireAt < Date.now()) {
        // 已过期 → 清除并返回 null
        wx.removeStorageSync('vocational_zzbm_verify_cache');
        return null;
      }
      return cache;
    } catch (e) {
      console.error('读取验证缓存失败：', e);
      return null;
    }
  },

  // 写入已报名身份二次验证的本地缓存
  _writeVerifyCache(sfzh, verifyToken, expireSeconds) {
    try {
      if (!sfzh || !verifyToken) return;
      const ttl = (typeof expireSeconds === 'number' && expireSeconds > 0) ? expireSeconds : 900;
      const cache = {
        sfzh,
        verifyToken,
        expireAt: Date.now() + ttl * 1000
      };
      wx.setStorageSync('vocational_zzbm_verify_cache', JSON.stringify(cache));
    } catch (e) {
      console.error('写入验证缓存失败：', e);
    }
  },

  // ==================== 提交表单 ====================

  // 提交表单
  async onSubmit() {
    console.log('提交检查 - isEditMode:', this.data.isEditMode, 'enrollmentId:', this.data.enrollmentId);

    // 新流程：需要先预创建报名记录
    if (!this.data.isEditMode && !this.data.enrollmentId) {
      wx.showModal({
        title: '请先完成报名流程',
        content: '请按步骤填写信息后再提交',
        showCancel: false,
        confirmText: '我知道了'
      });
      return;
    }

    // 先将身份证号转为大写
    let bmxs = this.data.bmxs;
    if (bmxs.sfzh) {
      bmxs.sfzh = bmxs.sfzh.toUpperCase();
      this.setData({ 'bmxs.sfzh': bmxs.sfzh });
    }

    // 检查名额（编辑模式如果专业未改则跳过）
    const majorChanged = this.data.originalBdzy && this.data.originalBdzy !== bmxs.bdzy;
    if ((!this.data.isEditMode || majorChanged) && this.data.remaining !== null && this.data.remaining <= 0) {
      wx.showToast({
        title: '您选择的专业已满，请选择其他专业',
        icon: 'none'
      });
      return;
    }

    this.setData({ submitDisabled: true });

    // 表单校验开始 - 验证所有字段
    const requiredFields = {
      xm: '姓名',
      xb: '性别',
      mz: '民族',
      zzmm: '政治面貌',
      hkxz: '户口类型',
      sfjdlk: '是否建档立卡',
      xsdh: '学生电话',
      jtxxdz: '家庭详细地址',
      byxxmc: '毕业学校名称',
      byxxssx1: '毕业学校所在省',
      byxxssx2: '毕业学校所在市',
      byxxssx3: '毕业学校所在区',
      jzxm: '家长姓名',
      jzdh: '家长电话',
      jzgx: '与家长关系',
      jzdlx: '居住地类型',
      xsly: '招生来源',
      zsdx: '招生对象',
      qd: '渠道',
      bdzy: '报考专业',
      sfqdxf: '是否购买校服'
    };
    for (const key in requiredFields) {
      if (!bmxs[key] && bmxs[key] !== 0) {
        this.showError(`请填写${requiredFields[key]}`)
        this.setData({ submitDisabled: false });
        return;
      }
    }

    // 身份证号校验
    if (!this.isIDCard(bmxs.sfzh)) {
      this.showError('身份证号格式不正确')
      this.setData({ submitDisabled: false });
      return;
    }

    // 电话号码校验
    const phoneReg = /^1[3-9]\d{9}$/;
    if (!phoneReg.test(bmxs.xsdh)) {
      this.showError('学生电话格式不正确')
      this.setData({ submitDisabled: false });
      return;
    }
    if (!phoneReg.test(bmxs.jzdh)) {
      this.showError('家长电话格式不正确')
      this.setData({ submitDisabled: false });
      return;
    }

    // 渠道介绍人校验
    if (bmxs.qd == 7 && !bmxs.qdjs) {
      this.showError('请填写渠道介绍人')
      this.setData({ submitDisabled: false });
      return;
    }

    try {
      // 编辑模式：调用更新接口
      if (this.data.isEditMode && this.data.editRecordId) {
        const updateRes = await post('/enrollment_query/update/vocational_zzbm', {
          query_code: this.data.editQueryCode,
          record_id: this.data.editRecordId,
          form_data: { ...this.data.bmxs }
        }, { loadingTitle: '保存中...' });

        wx.hideLoading();
        this.setData({ submitDisabled: false });
        this.showSuccess('修改成功');
        setTimeout(() => { wx.reLaunch({ url: '/pages/home/home' }); }, 1500);
        return;
      }

      // 新报名模式：调用更新接口补全信息
      const res = await post('/zzbm/update_info', {
        id: this.data.enrollmentId,
        xm: bmxs.xm,
        xb: bmxs.xb,
        mz: bmxs.mz,
        zzmm: bmxs.zzmm,
        sfzh: bmxs.sfzh,
        xsdh: bmxs.xsdh,
        jtxxdz: bmxs.jtxxdz,
        jzdlx: bmxs.jzdlx,
        hkxz: bmxs.hkxz,
        jzxm: bmxs.jzxm,
        jzgx: bmxs.jzgx,
        jzdh: bmxs.jzdh,
        bdzy: bmxs.bdzy,
        byxxssx1: bmxs.byxxssx1,
        byxxssx2: bmxs.byxxssx2,
        byxxssx3: bmxs.byxxssx3,
        byxxmc: bmxs.byxxmc,
        zsdx: bmxs.zsdx,
        sfjdlk: bmxs.sfjdlk,
        sflset: bmxs.sflset,
        sftwjrzn: bmxs.sftwjrzn,
        xsly: bmxs.xsly,
        qd: bmxs.qd,
        qdjs: bmxs.qdjs,
        sfqdxf: bmxs.sfqdxf,
        remark: bmxs.remark || '',
        is_complete: bmxs.is_complete
      }, { loadingTitle: '保存中...' });

      console.log('更新报名结果:', res);

      // 报名完成，获取查询码
      const queryCodeRes = await get('/zzbm/get_enrollment_detail', { id: this.data.enrollmentId }, { showLoading: false });
      const queryCode = queryCodeRes && queryCodeRes.query_code ? queryCodeRes.query_code : '';

      wx.hideLoading();
      this.setData({
        submitDisabled: false,
        showSuccessModal: true,
        successQueryCode: queryCode,
        successMajorName: this.data.bdzyArray && this.data.bdzyIndex && this.data.bdzyIndex[1] !== undefined
          ? this.data.bdzyArray[1][this.data.bdzyIndex[1]].cooperation_school + '-' + this.data.bdzyArray[1][this.data.bdzyIndex[1]].cooperation_major
          : ''
      });
    } catch (error) {
      this.showError(error)
      this.setData({ submitDisabled: false });
    }
  },

  // 成功弹窗操作
  copyQueryCode() {
    if (this.data.successQueryCode) {
      wx.setClipboardData({
        data: this.data.successQueryCode,
        success: () => {
          wx.showToast({ title: '已复制', icon: 'success' });
          // 复制后关闭弹窗，清除数据，返回首页
          setTimeout(() => {
            this.setData({ showSuccessModal: false });
            this.clearFormData();
            wx.reLaunch({ url: '/pages/home/home' });
          }, 800);
        }
      });
    }
  },

  closeSuccessModal() {
    this.setData({ showSuccessModal: false });
    if (this.data.isNewRegistration) {
      // 抢占名额成功：进入下一步继续完善信息
      wx.pageScrollTo({ scrollTop: 0, duration: 200 });
      this.setData({ currentStep: 2 });
    } else {
      // 正常提交成功：跳转缴费页
      const sfzh = this.data.bmxs.sfzh;
      wx.navigateTo({
        url: '/packageVocational/pages/vocational-new-payment/vocational-new-payment?idNumber=' + sfzh
      });
    }
  },

  // ==================== 推广参数处理方法 ====================

  // 处理推广参数
  handlePromotionParams(options) {
    // options.scene = 'introducer=王小华&major=计算机应用技术'
    // 检查是否有介绍人参数
    if (options && options.scene) {
      const scene = decodeURIComponent(options.scene)
      try {

        // 从options.scene中解析参数出所有的参数
        const params = {};
        scene.split('&').forEach(item => {
          const [key, value] = item.split('=');
          params[key] = value;
        });
        // base64.urlsafe_b64encode 编码还原为原始字符串
        let introducerName = params.uid;

        // 从参数中获取介绍人信息（可能是base64编码的）

        if (introducerName) {

          try {
            // 使用自定义的URL安全base64解码函数（兼容微信小程序）
            const decodedName = decodeUrlSafeBase64(introducerName);
            if (decodedName) {
              introducerName = decodedName;
            } else {
              // 如果解码失败，保持原始值
            }
          } catch (e) {
            // 如果解码失败，保持原始值
          }
        }

        // 验证介绍人是否在候选列表中
        const validIntroducer = this.data.introducerList.find(item => item.name === introducerName);

        if (validIntroducer) {
          // 设置渠道为"有认识的老师介绍"（索引6，值7）
          this.setData({
            qdIndex: 6,
            'bmxs.qd': 7,
            'bmxs.qdjs': introducerName,
            isPromotionEntry: true,
            promotionIntroducer: introducerName
          });

          // 保存数据
          this.saveFormData();

          // 显示成功提示
          this.showSuccess(`已自动选择介绍人: ${introducerName}`)

          // 记录推广来源（可用于统计）
          this.recordPromotionSource(introducerName);

        } else {
          // 介绍人不在列表中，显示警告
          wx.showModal({
            title: '参数错误',
            content: `介绍人"${introducerName}"不在候选列表中，请联系管理员确认。\n\n您仍可以手动选择其他介绍人。`,
            showCancel: true,
            cancelText: '手动选择',
            confirmText: '联系管理员',
            confirmColor: '#E86433',
            success: (res) => {
              if (res.confirm) {
                // 用户选择联系管理员
                this.contactAdmin();
              }
            }
          });

        }
      } catch (error) {
        console.error('处理介绍人参数时出错:', error);
        this.showError('参数解析失败')
      }
    }

    // 处理其他推广参数
    this.handleOtherPromotionParams(options);
  },

  // 记录推广来源（用于统计分析）
  recordPromotionSource(introducerName) {
    try {
      // 可以发送统计数据到服务器
      // console.log('推广统计:', {
      //   介绍人: introducerName,
      //   时间: new Date().toISOString(),
      //   页面: 'vocational-zzbm'
      // });

      // 这里可以调用统计API
      // wx.request({
      //   url: 'your-analytics-api',
      //   method: 'POST',
      //   data: { introducer: introducerName, timestamp: Date.now() }
      // });
    } catch (error) {
      console.error('记录推广来源失败:', error);
    }
  },

  // 处理其他推广参数
  handleOtherPromotionParams(options) {
    // 预设专业参数
    if (options && options.major) {
      console.log('检测到专业参数:', options.major);
      // 这里可以根据专业名称自动选择对应的专业
    }

    // 预设招生来源参数
    if (options && options.source) {
      console.log('检测到来源参数:', options.source);
      // 可以根据来源自动设置招生来源字段
    }

    // 推广活动标识
    if (options && options.campaign) {
      console.log('检测到活动参数:', options.campaign);
      // 可以用于统计不同推广活动的效果
    }
  },

  // 联系管理员
  contactAdmin() {
    wx.showModal({
      title: '联系管理员',
      content: '请联系招生办公室：\n电话：0855-8503999\n或咨询相关老师',
      showCancel: false,
      confirmText: '我知道了'
    });
  },

  // ==================== 推广链接生成工具 ====================

  // 生成推广链接（开发调试用）
  generatePromotionLink(introducerName) {
    const encodedName = encodeURIComponent(introducerName);
    const baseUrl = '/pages/vocational-zzbm/vocational-zzbm';
    const promotionUrl = `${baseUrl}?introducer=${encodedName}`;

    console.log('推广链接生成:', {
      介绍人: introducerName,
      链接: promotionUrl,
      完整路径: `pages/vocational-zzbm/vocational-zzbm?introducer=${encodedName}`
    });

    return promotionUrl;
  },

  // 生成二维码参数（用于生成小程序码）
  generateQRCodeParams(introducerName, options = {}) {
    const params = {
      introducer: introducerName,
      ...options
    };

    // 小程序码参数需要转换为字符串格式
    const paramString = Object.keys(params)
      .map(key => `${key}=${encodeURIComponent(params[key])}`)
      .join('&');

    console.log('二维码参数:', {
      原始参数: params,
      参数字符串: paramString,
      页面路径: 'pages/vocational-zzbm/vocational-zzbm'
    });

    return {
      page: 'pages/vocational-zzbm/vocational-zzbm',
      scene: paramString
    };
  },

  // ==================== 介绍人选择相关方法 ====================

  // 显示介绍人选择弹窗
  showIntroducerPicker() {
    this.setData({
      showIntroducerPopup: true
    });
    this.filterIntroducers();
  },

  // 隐藏介绍人选择弹窗
  hideIntroducerPicker() {
    this.setData({
      showIntroducerPopup: false,
      introducerSearchKeyword: '',
      selectedAlphabet: '全部'
    });
  },

  // 搜索介绍人
  onIntroducerSearch(e) {
    this.setData({
      introducerSearchKeyword: e.detail.value,
      selectedAlphabet: '全部' // 搜索时重置字母筛选
    });
    this.filterIntroducers();
  },

  // 清除搜索
  clearIntroducerSearch() {
    this.setData({
      introducerSearchKeyword: '',
      selectedAlphabet: '全部'
    });
    this.filterIntroducers();
  },

  // 选择字母筛选
  selectAlphabet(e) {
    const alphabet = e.currentTarget.dataset.alphabet;
    this.setData({
      selectedAlphabet: alphabet,
      introducerSearchKeyword: '' // 字母筛选时清除搜索
    });
    this.filterIntroducers();
    wx.vibrateShort(); // 触觉反馈
  },

  // 过滤介绍人列表
  filterIntroducers() {
    let filtered = this.data.introducerList;

    // 按字母筛选
    if (this.data.selectedAlphabet !== '全部') {
      filtered = filtered.filter(item => item.firstLetter === this.data.selectedAlphabet);
    }

    // 按关键词搜索
    if (this.data.introducerSearchKeyword) {
      const keyword = this.data.introducerSearchKeyword.toLowerCase();
      filtered = filtered.filter(item =>
        item.name.toLowerCase().includes(keyword) ||
        item.pinyin.toLowerCase().includes(keyword) ||
        item.firstLetter.toLowerCase().includes(keyword)
      );
    }

    // 按姓名排序
    filtered.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));

    this.setData({
      filteredIntroducers: filtered
    });
  },

  // 选择介绍人 - 点击即选择并关闭
  selectIntroducer(e) {
    const name = e.currentTarget.dataset.name;

    this.setData({
      'bmxs.qdjs': name
    });

    // 立即关闭弹窗
    this.hideIntroducerPicker();

    // 保存表单数据
    this.saveFormData();

    // 触觉反馈和成功提示
    wx.vibrateShort();
    this.showSuccess(`已选择: ${name}`)
  },

  // 验证身份证号码
  isIDCard(s) {
    if (!s || (s.length !== 15 && s.length !== 18)) {
      return false;
    }

    let Ai;
    if (s.length === 18) {
      Ai = s.substring(0, 17);
    } else {
      Ai = s.substring(0, 6) + "19" + s.substring(6, 15);
    }

    // 检查是否为数字
    if (!/^\d+$/.test(Ai)) {
      return false;
    }

    // 验证地区代码
    const areaCodeReg = /^(1[1-5]|2[1-3]|3[1-7]|4[1-6]|5[0-4]|6[1-5]|8[12]|91)\d{4}$/;
    if (!areaCodeReg.test(Ai.substring(0, 6))) {
      return false;
    }

    // 验证出生日期
    const birthYear = parseInt(Ai.substring(6, 10));
    const birthMonth = parseInt(Ai.substring(10, 12));
    const birthDay = parseInt(Ai.substring(12, 14));

    const birthDate = new Date(birthYear, birthMonth - 1, birthDay);
    const currentDate = new Date();
    const minDate = new Date(1870, 0, 1);

    if (birthDate.getFullYear() !== birthYear ||
        birthDate.getMonth() !== birthMonth - 1 ||
        birthDate.getDate() !== birthDay ||
        birthDate > currentDate ||
        birthDate < minDate) {
      return false;
    }

    // 如果是18位身份证，验证校验码
    if (s.length === 18) {
      const arrVerifyCode = ['1', '0', 'x', '9', '8', '7', '6', '5', '4', '3', '2'];
      const Wi = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];

      let AiPlusWi = 0;
      for (let i = 0; i < 17; i++) {
        AiPlusWi += parseInt(Ai.charAt(i)) * Wi[i];
      }

      const modValue = AiPlusWi % 11;
      const strVerifyCode = arrVerifyCode[modValue];
      const calculatedId = Ai + strVerifyCode;

      if (s.toLowerCase() !== calculatedId) {
        return false;
      }
    }

    return true;
  }
})