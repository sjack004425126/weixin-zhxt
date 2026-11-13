const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    formData: {
      xm: '', // 姓名
      xb: '', // 性别
      csrq: '', // 出生日期
      mz: '', // 民族
      zzmm: '', // 政治面貌
      zjlx: '', // 证件类型
      zjh: '', // 证件号
      sj: '', // 手机
      jtdh: '', // 家庭电话
      yx: '', // 邮箱
      dwdh: '', // 单位电话
      dzzch: '', // 电子注册号
      gzdw: '', // 工作单位
      bysxdw: '', // 毕业实习单位
      jlhcf: '', // 奖励或处分
      xlcc: '', // 学历层次
      xslb: '', // 学生类别
      xxzy: '', // 学习专业
      rxsjn: '', // 入学年份
      rxsjj: '', // 入学季节
      bysjn: '', // 毕业年份
      bysjy: '', // 毕业月份
      bylwtm: '', // 毕业论文题目
      zwjd: '', // 自我鉴定
      study_experience: [], // 学习经历
    },
    loading: false,
    showDatePicker: false,
    currentDate: new Date().getTime(),
    minDate: new Date(1990, 0, 1).getTime(),
    maxDate: new Date().getTime(),
    activeStudyIndex: 0,
    activeTimeType: '',
    showResetConfirm: false,
    isGraduate: false, // 是否已毕业
    isLocked: false, // 添加锁定状态
    focusField: '', // 当前需要高亮的字段
    showPoliticalStatusPicker: false,
    politicalStatusOptions: [
      '群众',
      '中国共产党党员',
      '中国共产党预备党员',
      '中国共产主义青年团团员',
      '民革党员',
      '民盟盟员',
      '民建会员',
      '民进会员',
      '农工党党员',
      '致公党党员',
      '九三学社社员',
      '台盟盟员'
    ]
  },

  onLoad() {
    this.getGraduateFormInfo();
  },

  // 获取毕业生登记表信息
  async getGraduateFormInfo() {
    try{
      const resquest = await tokenGet('/student/get_graduate_registration',{},{loadingTitle: '获取毕业生登记表信息...'});
      const { is_graduate, registration } = resquest || {};
      const raw = registration || {};
      // van-field 的 value 只接受 String，传 null 会刷屏告警；后端 null 一律转为空串
      const str = (v) => (v === null || v === undefined ? '' : String(v));
      const formData = {
        xm: str(raw.xm),
        xb: str(raw.xb),
        csrq: str(raw.csrq),
        mz: str(raw.mz),
        zzmm: str(raw.zzmm),
        zjlx: str(raw.zjlx),
        zjh: str(raw.zjh),
        sj: str(raw.sj),
        jtdh: str(raw.jtdh),
        yx: str(raw.yx),
        dwdh: str(raw.dwdh),
        dzzch: str(raw.dzzch),
        gzdw: str(raw.gzdw),
        bysxdw: str(raw.bysxdw),
        jlhcf: str(raw.jlhcf),
        xlcc: str(raw.xlcc),
        xslb: str(raw.xslb),
        xxzy: str(raw.xxzy),
        rxsjn: str(raw.rxsjn),
        rxsjj: str(raw.rxsjj),
        bysjn: str(raw.bysjn),
        bysjy: str(raw.bysjy),
        bylwtm: str(raw.bylwtm),
        zwjd: str(raw.zwjd),
        study_experience: Array.isArray(raw.study_experience)
          ? raw.study_experience.map((it) => ({
              qsj: str(it && it.qsj),
              zsj: str(it && it.zsj),
              xx: str(it && it.xx)
            }))
          : []
      };

      this.setData({
        formData,
        isGraduate: !!is_graduate,
        isLocked: !!(raw && raw.zt)
      });
    }catch(err){
      this.showError(err.message || "获取毕业生登记表信息失败");
    }
  },


  onInputChange(e) {
    // 锁定状态下不允许修改
    if (this.data.isLocked) return;

    const field = e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.field;
    if (!field) return;
    const detail = e.detail;
    // van-field 的 bind:change detail 即为字符串值；兼容对象形式；null 一律转空串
    let v = '';
    if (typeof detail === 'string') v = detail;
    else if (detail && typeof detail.value === 'string') v = detail.value;
    else if (detail !== null && detail !== undefined) v = String(detail);
    this.setData({
      [`formData.${field}`]: v
    });
  },

  // 滚动到指定字段
  scrollToField(field) {
    // 字段与表单组的映射关系
    const fieldToGroupMap = {
      // 基本信息
      'xm': 'basic-info',
      'xb': 'basic-info',
      'csrq': 'basic-info',
      'mz': 'basic-info',
      'zzmm': 'basic-info',
      // 证件信息
      'zjlx': 'id-info',
      'zjh': 'id-info',
      'dzzch': 'id-info',
      // 联系方式
      'sj': 'contact-info',
      'jtdh': 'contact-info',
      'yx': 'contact-info',
      'dwdh': 'contact-info',
      // 学习信息
      'xlcc': 'study-info',
      'xslb': 'study-info',
      'xxzy': 'study-info',
      'rxsjn': 'study-info',
      'rxsjj': 'study-info',
      // 毕业信息
      'bysjn': 'graduate-info',
      'bysjy': 'graduate-info',
      'bylwtm': 'graduate-info',
      'bysxdw': 'graduate-info',
      'gzdw': 'graduate-info',
      'jlhcf': 'graduate-info',
      // 自我鉴定
      'zwjd': 'self-evaluation'
    };

    const groupId = fieldToGroupMap[field];
    if (groupId) {
      // 滚动到对应的表单组
      wx.pageScrollTo({
        selector: `#${groupId}`,
        duration: 500,
        success: () => {
          // 滚动完成后，设置焦点字段用于高亮显示
          this.setData({
            focusField: field
          });
          // 2秒后清除高亮
          setTimeout(() => {
            this.setData({
              focusField: ''
            });
          }, 2000);
        }
      });
    }
  },

  async submitForm() {
    // 检查所有字段是否为空
    const formFields = {
      xm: '姓名',
      xb: '性别',
      csrq: '出生日期',
      mz: '民族',
      zzmm: '政治面貌',
      zjlx: '证件类型',
      zjh: '证件号',
      sj: '手机',
      jtdh: '家庭电话',
      yx: '邮箱',
      dwdh: '单位电话',
      dzzch: '电子注册号',
      gzdw: '工作单位',
      bysxdw: '毕业实习单位',
      jlhcf: '奖励或处分',
      xlcc: '学历层次',
      xslb: '学生类别',
      xxzy: '学习专业',
      rxsjn: '入学年份',
      rxsjj: '入学季节',
      bysjn: '毕业年份',
      bysjy: '毕业月份',
      bylwtm: '毕业论文题目',
      zwjd: '自我鉴定'
    };

    const formData = this.data.formData;

    // 检查每个字段
    const fields = Object.keys(formFields);
    for (let i = 0; i < fields.length; i++) {
      const field = fields[i];
      const label = formFields[field];
      const value = formData[field];
      
      // 确保值存在且不为空（转换为字符串后去除空格）
      if (!value || String(value).trim() === '') {
        this.showError(`${label}为空，如果没有相关信息，请填写"无"`);
        // 跳转到对应的字段位置
        this.scrollToField(field);
        return;
      }
    }

    // 验证学习经历
    const study_experience = formData.study_experience;
    if (!study_experience.length) {
      this.showError('请至少添加一条学习经历');
      return;
    }

    for (let i = 0; i < study_experience.length; i++) {
      const item = study_experience[i];
      if (!item.qsj || !item.zsj || !item.xx) {
        this.showError(`请完善第${i + 1}条学习经历`);
        return;
      }
    }



    // 创建提交数据的副本
    const submitData = { ...formData };
    const studyExpData = submitData.study_experience || [];
    delete submitData.study_experience;

    // 先清空所有学习经历相关字段
    for(let i = 1; i <= 5; i++) {
      submitData[`qsj${i}`] = '';
      submitData[`zsj${i}`] = '';
      submitData[`xx${i}`] = '';
    }

    // 填充实际的学习经历数据
    studyExpData.forEach((item, index) => {
      const num = index + 1;
      submitData[`qsj${num}`] = item.qsj || '';
      submitData[`zsj${num}`] = item.zsj || '';
      submitData[`xx${num}`] = item.xx || '';
    });


    try{
      const resquest = await tokenPost('/student/save_graduate_registration',submitData,{loadingTitle: '提交毕业生登记表...'});
      this.showSuccess("提交毕业生登记表成功");
      setTimeout(() => {
        wx.navigateTo({
          url: '/packageStudent/pages/my/my'
        });
      }, 1500);
    }catch(err){
      this.showError(err.message || "提交毕业生登记表失败");
    }
  },
  goHome(){
    wx.navigateTo({
      url: '/packageStudent/pages/my/my'
    });
  },

  // 添加学习经历
  addStudyExp() {
    // 锁定状态下不允许修改
    if (this.data.isLocked) return;

    const study_experience = this.data.formData.study_experience;
    if (study_experience.length >= 5) return;
    
    study_experience.push({
      qsj: '',
      zsj: '',
      xx: ''
    });
    
    this.setData({
      'formData.study_experience': study_experience
    });
  },

  // 删除学习经历
  deleteStudyExp(e) {
    // 锁定状态下不允许修改
    if (this.data.isLocked) return;

    const ds = (e.currentTarget && e.currentTarget.dataset) || {};
    const index = Number(ds.index);
    if (isNaN(index)) return;
    const study_experience = (this.data.formData && this.data.formData.study_experience) || [];
    if (!study_experience[index]) return;
    study_experience.splice(index, 1);
    this.setData({
      'formData.study_experience': study_experience
    });
  },

  // 学习经历输入变化
  onStudyExpChange(e) {
    if (this.data.isLocked) return;
    const ds = (e.currentTarget && e.currentTarget.dataset) || {};
    const index = ds.index;
    const type = ds.type;
    if (index === undefined || !type) return;
    const study_experience = this.data.formData.study_experience || [];
    if (!study_experience[index]) return;
    const detail = e.detail;
    let v = '';
    if (typeof detail === 'string') v = detail;
    else if (detail && typeof detail.value === 'string') v = detail.value;
    else if (detail !== null && detail !== undefined) v = String(detail);
    study_experience[index][type] = v;
    this.setData({
      'formData.study_experience': study_experience
    });
  },

  // 显示日期选择器
  showDatePicker(e) {
    // 锁定状态下不允许修改
    if (this.data.isLocked) return;

    const ds = (e.currentTarget && e.currentTarget.dataset) || {};
    const index = ds.index;
    const type = ds.type;
    const study_experience = this.data.formData.study_experience || [];
    const row = study_experience[index];
    if (row === undefined || !type) return;
    const currentValue = row[type] || '';

    let currentDate = this.data.currentDate;
    if (typeof currentValue === 'string' && currentValue.indexOf('-') > 0) {
      const parts = currentValue.split('-');
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10);
      if (!isNaN(year) && !isNaN(month)) {
        currentDate = new Date(year, month - 1).getTime();
      }
    }

    this.setData({
      showDatePicker: true,
      activeStudyIndex: index,
      activeTimeType: type,
      currentDate
    });
  },

  // 关闭日期选择器
  onDatePickerClose() {
    this.setData({
      showDatePicker: false
    });
  },

  // 确认日期选择
  onDatePickerConfirm(e) {
    const detail = (e && e.detail !== undefined) ? e.detail : undefined;
    // van-datetime-picker confirm 的 detail 为时间戳；兼容对象形式
    let ts = detail;
    if (detail && typeof detail === 'object') {
      ts = detail.value !== undefined ? detail.value : detail.innerValue;
    }
    const date = new Date(ts);
    if (isNaN(date.getTime())) {
      this.setData({ showDatePicker: false });
      return;
    }
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const dateStr = `${year}-${month}`;

    const activeStudyIndex = Number(this.data.activeStudyIndex);
    const activeTimeType = this.data.activeTimeType;
    const study_experience = this.data.formData.study_experience || [];
    if (!study_experience[activeStudyIndex] || !activeTimeType) {
      this.setData({ showDatePicker: false });
      return;
    }

    // 验证起止时间的合理性
    if (activeTimeType === 'zsj') {
      const qsj = study_experience[activeStudyIndex].qsj;
      if (qsj && dateStr < qsj) {
        wx.showToast({
          title: '终止时间不能早于起始时间',
          icon: 'none'
        });
        return;
      }
    } else if (activeTimeType === 'qsj') {
      const zsj = study_experience[activeStudyIndex].zsj;
      if (zsj && dateStr > zsj) {
        wx.showToast({
          title: '起始时间不能晚于终止时间',
          icon: 'none'
        });
        return;
      }
    }
    
    study_experience[activeStudyIndex][activeTimeType] = dateStr;
    
    this.setData({
      'formData.study_experience': study_experience,
      showDatePicker: false
    });
  },

  // 显示政治面貌选择器
  showPoliticalStatusPicker() {
    if (this.data.isLocked) return;
    this.setData({
      showPoliticalStatusPicker: true
    });
  },

  // 关闭政治面貌选择器
  onPoliticalStatusPickerClose() {
    this.setData({
      showPoliticalStatusPicker: false
    });
  },

  // 确认选择政治面貌
  onPoliticalStatusConfirm(event) {
    const detail = (event && event.detail !== undefined) ? event.detail : undefined;
    // van-picker confirm 的 detail 为 {value, index}；兼容字符串/数组形式，后端只存文本
    let value = detail;
    if (detail && typeof detail === 'object' && detail.value !== undefined) {
      value = detail.value;
    }
    if (Array.isArray(value)) {
      value = value.length ? value[0] : '';
    }
    if (value && typeof value === 'object') {
      value = value.text !== undefined ? value.text : (value.value !== undefined ? value.value : '');
    }
    if (value === null || value === undefined) value = '';
    else value = String(value);
    this.setData({
      'formData.zzmm': value,
      showPoliticalStatusPicker: false
    });
  },
},{
  requireAuth: true,
  userType: 'open_student'
}) 