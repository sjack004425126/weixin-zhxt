const app = getApp();
const { createPage } = require('../../../utils/page-mixin');
const { get, post } = require('../../../utils/request');
const { getAreaBookFee, DEFAULT_AREA } = require('../../../config/area-config');


createPage({
  data: {
    formData: {
      name: '',
      id_card: '',
      phone: '',
      major_id: null
    },
    loading: false,
    // 查询码
    queryCodeInput: '',
    isQuerying: false,
    showQueryCodePopup: false,
    paymentInfo: null,
    queryMajorInfo: null,
    // 地区相关数据
    currentArea: DEFAULT_AREA,
    calculatedBookFee: 0,
    calculatedBookFeeDisplay: '0.00', // 格式化后的书费显示
    totalAmount: 0,
    totalAmountDisplay: '0.00', // 格式化后的总金额显示
    bookFeeNote: '',
    // 专业选择相关数据
    majorData: [],
    levelIndex: 0,
    typeIndex: 0,
    majorIndex: 0,
    levels: [],
    types: [],
    majors: [],
    showMajorPicker: false,
    columns: [],
    typeNames: {
      1: '文史类',
      2: '财经类',
      3: '理工类',
      4: '一村一',
      5: '成高类'
    }
  },

  onLoad(options) {
    // 获取地区参数
    const area = options.area || DEFAULT_AREA;
    this.setData({
      currentArea: area
    });
    this.getMajorList();
    
    // 如果有身份证号参数（从报名页跳转来），自动填充
    if (options.idNumber) {
      this.setData({ 'formData.id_card': options.idNumber });
    }
  },

  // ==================== 查询码查询 ====================

  onQueryCodeInput(e) {
    this.setData({ queryCodeInput: (e.detail.value || '').toUpperCase() });
  },

  // 打开查询码弹窗
  openQueryCodePopup() {
    this.setData({
      showQueryCodePopup: true,
      queryCodeInput: '' // 清空上次的输入
    });
  },

  // 关闭查询码弹窗
  closeQueryCodePopup() {
    this.setData({
      showQueryCodePopup: false,
      queryCodeInput: '' // 关闭时清空输入
    });
  },

  async verifyQueryCode() {
    const code = this.data.queryCodeInput.trim();
    if (!code || code.length < 8) {
      this.showError('请输入至少8位查询码');
      return;
    }
    
    this.setData({ isQuerying: true });
    try {
      const res = await post('/enrollment_query/verify_payment', { query_code: code }, { loadingTitle: '查询中...' });
      
      // 关闭弹窗
      this.closeQueryCodePopup();
      
      const order = res.order;
      const major = res.major;
      
      // 填充表单
      this.setData({
        'formData.name': order.name || '',
        'formData.id_card': order.id_card || '',
        'formData.phone': order.phone || '',
        paymentInfo: {
          has_paid: order.has_paid,
          status_text: order.status_text,
          amount: order.amount,
          pay_time: order.pay_time,
          order_no: order.order_no,
          tuition: order.tuition,
          book_fee: order.book_fee,
        },
        queryMajorInfo: major
      });
      
      // 自动选中专业（根据 major.id 匹配 majorData）
      if (major && major.id && this.data.majorData && this.data.majorData.length > 0) {
        this._autoSelectMajor(major.id);
      }

      // 显示提示
      if (order.has_paid) {
        this.showSuccess('已加载报名信息，订单已完成缴费');
      } else {
        this.showSuccess('已加载报名信息，可修改后重新缴费');
      }
    } catch (error) {
      this.showError(error);
    } finally {
      this.setData({ isQuerying: false });
    }
  },



  // 获取专业列表
  // 三级联动顺序：类型 → 层次 → 专业
  async getMajorList() {
    try{
      const result = await get('/freshman_tuition/get_majors_all',{},{loadingTitle: '正在加载专业信息...'});
      const majorData = result;
      const firstType = majorData[0];
      const firstLevel = firstType.levels[0];
      
      this.setData({
        majorData,
        typeIndex: 0,
        levelIndex: 0,
        majorIndex: 0,
        columns: [{
          values: majorData.map(item => item.name)
        }, {
          values: firstType.levels.map(level => level.name)
        }, {
          values: firstLevel.majors.map(major => major.name)
        }]
      });
    } catch (err) {
      this.showError(err)
    }

  },

  // 显示专业选择器
  showMajorPickerPopup() {
    this.setData({ showMajorPicker: true });
  },

  // 关闭专业选择器
  onMajorPickerClose() {
    this.setData({ showMajorPicker: false });
  },

  // 专业选择器改变
  // 三级联动顺序：类型 → 层次 → 专业
  onMajorPickerChange(e) {
    const { picker, value, index } = e.detail;

    try {
      const currentValues = picker.getValues();
      const selectedValue = Array.isArray(value) ? value[index] : value;

      // 如果类型改变（第一列）
      if (index === 0) {
        const typeIndex = this.data.majorData.findIndex(item => item.name === selectedValue);
        if (typeIndex === -1) return;

        const levels = this.data.majorData[typeIndex].levels;
        
        // 如果该类型下没有层次数据，清空二级和三级
        if (!levels || levels.length === 0) {
          this.setData({
            typeIndex,
            levelIndex: 0,
            majorIndex: 0
          });
          picker.setColumnValues(1, []);
          picker.setColumnValues(2, []);
          setTimeout(() => {
            picker.setIndexes([typeIndex, 0, 0]);
          }, 50);
          return;
        }

        const levelValues = levels.map(level => level.name);
        const firstLevel = levels[0];
        const majorValues = firstLevel.majors.map(major => major.name);

        this.setData({
          typeIndex,
          levelIndex: 0,
          majorIndex: 0
        });

        picker.setColumnValues(1, levelValues);
        picker.setColumnValues(2, majorValues);

        setTimeout(() => {
          picker.setIndexes([typeIndex, 0, 0]);
        }, 50);
      }
      // 如果层次改变（第二列）
      else if (index === 1) {
        const typeIndex = this.data.majorData.findIndex(item => item.name === currentValues[0]);
        if (typeIndex === -1) return;

        const levels = this.data.majorData[typeIndex].levels;
        const selectedLevel = levels.find(level => level.name === selectedValue);
        if (!selectedLevel) return;

        const majorValues = selectedLevel.majors.map(major => major.name);
        const levelIndex = levels.indexOf(selectedLevel);

        this.setData({
          levelIndex,
          majorIndex: 0
        });

        picker.setColumnValues(2, majorValues);

        setTimeout(() => {
          const currentIndexes = picker.getIndexes();
          picker.setIndexes([currentIndexes[0], levelIndex, 0]);
        }, 50);
      }
      // 如果专业改变（第三列）
      else if (index === 2) {
        const typeIndex = this.data.majorData.findIndex(item => item.name === currentValues[0]);
        if (typeIndex === -1) return;

        const levels = this.data.majorData[typeIndex].levels;
        const selectedLevel = levels.find(level => level.name === currentValues[1]);
        if (!selectedLevel) return;

        const majorIndex = selectedLevel.majors.findIndex(major => major.name === selectedValue);
        if (majorIndex !== -1) {
          this.setData({ majorIndex });
        }
      }
    } catch (error) {
      console.error('选择器改变错误:', error);
    }
  },

  // 确认专业选择
  // 三级联动顺序：类型 → 层次 → 专业
  onMajorPickerConfirm(e) {
    try {
      const values = e.detail.value;

      // 找到类型（第一列）
      const typeIndex = this.data.majorData.findIndex(item => item.name === values[0]);
      if (typeIndex === -1) {
        console.error('未找到类型:', values[0], '可用类型:', this.data.majorData.map(item => item.name));
        throw new Error('未找到对应的类型');
      }

      // 找到层次（第二列）
      const levels = this.data.majorData[typeIndex].levels;
      const selectedLevel = levels.find(level => level.name === values[1]);
      if (!selectedLevel) {
        console.error('未找到层次:', values[1], '可用层次:', levels.map(level => level.name));
        throw new Error('未找到对应的层次');
      }

      // 找到专业（第三列）
      const selectedMajor = selectedLevel.majors.find(major => major.name === values[2]);
      if (!selectedMajor) {
        console.error('未找到专业:', values[2], '可用专业:', selectedLevel.majors.map(major => major.name));
        throw new Error('未找到对应的专业');
      }

      // 验证专业数据
      if (!selectedMajor.tuition || selectedMajor.tuition < 0) {
        throw new Error('专业学费数据异常');
      }

      // 重新计算地区书费（基于当前地区）
      const calculatedBookFee = this.calculateBookFee(selectedMajor.id, selectedMajor.books);
      // 学费转换为分 + 书费（已经是分）
      const totalAmount = (selectedMajor.tuition * 100) + calculatedBookFee;

      // 准备更新数据
      const updateData = {
        showMajorPicker: false,
        typeIndex,
        levelIndex: levels.indexOf(selectedLevel),
        'formData.major_id': selectedMajor.id,
        selectedType: values[0],
        selectedLevel: values[1],
        selectedMajor: {
          name: selectedMajor.name,
          tuition: selectedMajor.tuition,
          books: selectedMajor.books
        },
        calculatedBookFee: calculatedBookFee,
        calculatedBookFeeDisplay: (calculatedBookFee / 100).toFixed(2),
        totalAmount: totalAmount,
        totalAmountDisplay: (totalAmount / 100).toFixed(2),
        bookFeeNote: this.getBookFeeNote(selectedMajor.id)
      };

      // 更新状态
      this.setData(updateData);
    } catch (error) {
      console.error('专业选择错误:', error);
      wx.showToast({
        title: '专业选择出错，请重试',
        icon: 'none'
      });
    }
  },

  // 输入框内容变化处理
  onInputChange(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({
      [`formData.${field}`]: e.detail
    });
  },

  // 根据专业ID自动选中专业选择器
  _autoSelectMajor(majorId) {
    const majorData = this.data.majorData;
    for (let ti = 0; ti < majorData.length; ti++) {
      const type = majorData[ti];
      if (!type.levels) continue;
      for (let li = 0; li < type.levels.length; li++) {
        const level = type.levels[li];
        if (!level.majors) continue;
        for (let mi = 0; mi < level.majors.length; mi++) {
          const major = level.majors[mi];
          if (major.id === majorId) {
            // 找到了，设置选中状态
            const calculatedBookFee = this.calculateBookFee(major.id, major.books);
            const totalAmount = (major.tuition * 100) + calculatedBookFee;
            this.setData({
              typeIndex: ti,
              levelIndex: li,
              majorIndex: mi,
              'formData.major_id': major.id,
              selectedType: type.name,
              selectedLevel: level.name,
              selectedMajor: {
                name: major.name,
                tuition: major.tuition,
                books: major.books
              },
              calculatedBookFee: calculatedBookFee,
              calculatedBookFeeDisplay: (calculatedBookFee / 100).toFixed(2),
              totalAmount: totalAmount,
              totalAmountDisplay: (totalAmount / 100).toFixed(2),
              bookFeeNote: this.getBookFeeNote(major.id)
            });
            return;
          }
        }
      }
    }
  },

  // 提交表单
  async submitForm() {
    const that = this;
    // 表单验证
    if (!this.validateForm()) return;
    try{
        // 获取openid_code
        const openid_code = await app.getOpenid_code();


        // 检查openid_code是否获取成功
        if (!openid_code) {
          this.showError('获取openid_code失败，请重试');
          return;
        }

        const payData = {
          code: openid_code, // 直接使用openid_code，不需要.code
          name: this.data.formData.name,
          id_card: this.data.formData.id_card,
          phone: this.data.formData.phone,
          major_id: this.data.formData.major_id,
          area: this.data.currentArea
        };



        const request = await post('/freshman_tuition/freshman_prePay', payData, {loadingTitle: '正在生成支付参数...'});
        // 得到支付参数，在小程序拉起支付页面
        wx.requestPayment({
          timeStamp: request.timeStamp,
          nonceStr: request.nonceStr,
          package: request.package,
          signType: request.signType,
          paySign: request.paySign,
          orderNo: request.orderNo,
          success: function () {
            // 支付成功,更新订单状态
            // setTimeout(async () => {
            //   await post('/freshman_tuition/updatePayStatus', {orderNo: res.orderNo}, {loadingTitle: '正在更新订单状态...'});
            // }, 1000);
            that.showSuccess('支付成功');
          },
            fail: (err) => {
            that.showError(err.errMsg);
          }
        });
    } catch (err) {
      that.showError(err)
    }








  },

  // 添加表单验证方法
  validateForm() {
    const { name, id_card, phone, major_id } = this.data.formData;
    
    if (!name) {
      this.showError('请输入姓名');
      return false;
    }
    
    if (!id_card) {
      this.showError('请输入身份证号');
      return false;
    }


    // 身份证号校验
    if (!this.isIDCard(id_card.toUpperCase())) {
      this.showError('身份证号格式不正确');
      return false;
    }
    
    if (!phone) {
      this.showError('请输入手机号');
      return false;
    }
    
    // 手机号验证
    const phoneReg = /^1[3-9]\d{9}$/;
    if (!phoneReg.test(phone)) {
      this.showError('手机号格式不正确');
      return false;
    }
    
    if (!major_id) {
      this.showError('请选择专业');
      return false;
    }
    
    return true;
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
  },

  // 计算书费
  calculateBookFee(majorId, defaultBookFee) {
    const bookFeeInYuan = getAreaBookFee(this.data.currentArea, majorId, defaultBookFee);
    return bookFeeInYuan * 100; // 转换为分
  },

  // 获取书费说明
  getBookFeeNote(majorId) {
    const { currentArea } = this.data;

    if (currentArea === DEFAULT_AREA) {
      return '按专业标准收费';
    }

    if (currentArea === '三穗' && (majorId == 26 || majorId == 73)) {
      return '三穗地区特殊专业，书费为350元/年';
    }

    if (currentArea !== DEFAULT_AREA) {
      return `${currentArea}地区统一书费标准`;
    }

    return '';
  },

  // 首页导航
  goHome() {
    wx.switchTab({
      url: '/pages/my-center/my-center'
    });
  },

  // 跳转到报名情况查询页面
  goToEnrollmentQuery() {
    wx.navigateTo({
      url: '/packageEnroll/pages/enrollment-query/enrollment-query',
      fail: (err) => {
        console.error('跳转报名情况查询失败:', err);
      }
    });
  }


});
 