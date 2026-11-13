const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost, tokenRequest } = require('../../../utils/request');

createPage({
  data: {
    formData: {
      qjlb: '',
      qjsy: '',
      qjkssj: '',
      qjjssj: '',
      xslxxl: '',
      xslxjtgj: '',
      qjkssj_time: '', // 开始时间的时分
      qjjssj_time: ''  // 结束时间的时分
    },
    leaveTypes: ['病假', '事假'],
    showTypePicker: false,
    showCalendar: false,
    showStartTimePicker: false,
    showEndTimePicker: false,
    minDate: new Date().getTime(),
    maxDate: new Date(new Date().getFullYear() + 1, 11, 31).getTime(),
    loading: false,
    promised: false,
    isEdit: false,
    leaveId: null,
    dateTimeFormatter: null,
    timeColumns: null,
    startTimeColumns: null,
    endTimeColumns: null,
    selectedDateRange: null,
    dateRangeDisplay: '',
    durationDisplay: ''
  },

  onLoad(options) {
    const timeColumns = this.generateTimeColumns();

    // 默认开始时间为当前时间
    const now = new Date();
    const nowHour = String(now.getHours()).padStart(2, '0');
    const nowMinute = String(now.getMinutes()).padStart(2, '0');
    const startTime = `${nowHour}:${nowMinute}`;

    // 默认结束时间为当前时间+1小时
    const endDate = new Date(now.getTime() + 60 * 60 * 1000);
    const endHour = String(endDate.getHours()).padStart(2, '0');
    const endMinute = String(endDate.getMinutes()).padStart(2, '0');
    const endTime = `${endHour}:${endMinute}`;

    this.setData({
      timeColumns: timeColumns,
      startTimeColumns: this.buildColumnsWithDefault(timeColumns, nowHour, nowMinute),
      endTimeColumns: this.buildColumnsWithDefault(timeColumns, endHour, endMinute),
      'formData.qjkssj_time': startTime,
      'formData.qjjssj_time': endTime
    });
    
    if (options.id) {
      this.setData({
        isEdit: true,
        leaveId: parseInt(options.id)
      });
      this.loadLeaveDetail(options.id);
    }
  },

  // 构建带默认选中的列数据
  buildColumnsWithDefault(timeColumns, hour, minute) {
    const hourIdx = parseInt(hour, 10);
    const minuteIdx = parseInt(minute, 10);
    return [
      { values: timeColumns[0].values, defaultIndex: hourIdx },
      { values: timeColumns[1].values, defaultIndex: minuteIdx }
    ];
  },

  // 生成时间选择器的列（小时:分钟）
  generateTimeColumns() {
    const hours = [];
    const minutes = [];
    
    for (let i = 0; i < 24; i++) {
      hours.push({
        text: `${String(i).padStart(2, '0')}时`,
        value: String(i).padStart(2, '0')
      });
    }
    
    for (let i = 0; i < 60; i++) {
      minutes.push({
        text: `${String(i).padStart(2, '0')}分`,
        value: String(i).padStart(2, '0')
      });
    }
    
    return [
      { values: hours },
      { values: minutes }
    ];
  },

  async loadLeaveDetail(id) {
    try {
      const res = await tokenGet(`/student/leave/detail/${id}`);
      const data = res;
      
      // 解析开始和结束时间
      let qjkssj_time = '08:00';
      let qjjssj_time = '18:00';
      let dateRangeDisplay = '';
      
      if (data.qjkssj) {
        const startTimeParts = data.qjkssj.split(' ');
        if (startTimeParts.length > 1) {
          qjkssj_time = startTimeParts[1].substring(0, 5); // 取 HH:mm
        }
      }
      
      if (data.qjjssj) {
        const endTimeParts = data.qjjssj.split(' ');
        if (endTimeParts.length > 1) {
          qjjssj_time = endTimeParts[1].substring(0, 5); // 取 HH:mm
        }
      }
      
      // 设置日期范围显示
      if (data.qjkssj && data.qjjssj) {
        const startDate = data.qjkssj.split(' ')[0];
        const endDate = data.qjjssj.split(' ')[0];
        dateRangeDisplay = `${startDate} 至 ${endDate}`;
      }
      
      this.setData({
        formData: {
          qjlb: data.qjlb || '',
          qjsy: data.qjsy || '',
          qjkssj: data.qjkssj || '',
          qjjssj: data.qjjssj || '',
          xslxxl: data.xslxxl || '',
          xslxjtgj: data.xslxjtgj || '',
          qjkssj_time: qjkssj_time,
          qjjssj_time: qjjssj_time
        },
        dateRangeDisplay: dateRangeDisplay,
        startTimeColumns: this.buildColumnsWithDefault(this.data.timeColumns, qjkssj_time.split(':')[0], qjkssj_time.split(':')[1]),
        endTimeColumns: this.buildColumnsWithDefault(this.data.timeColumns, qjjssj_time.split(':')[0], qjjssj_time.split(':')[1])
      });
      this.calcDuration();
    } catch (error) {
      this.showError('获取请假详情失败，请重试');
    }
  },

  onInputChange(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({
      [`formData.${field}`]: e.detail
    });
  },

  onReasonInput(e) {
    const value = e.detail.value || '';
    const length = value.length;
    const remaining = 200 - length;
    
    if (remaining <= 20 && remaining > 0) {
      console.log(`还可以输入${remaining}个字符`);
    } else if (remaining === 0) {
      this.showError('已达到字数上限（200个字符）');
    }
  },

  showTypePicker() {
    this.setData({ showTypePicker: true });
  },

  onTypePickerClose() {
    this.setData({ showTypePicker: false });
  },

  onTypeConfirm(e) {
    const { value } = e.detail;
    this.setData({
      'formData.qjlb': value,
      showTypePicker: false
    });
  },

  showStartTimePicker() {
    if (!this.data.formData.qjkssj) {
      this.showError('请先选择请假日期');
      return;
    }
    // 更新picker默认选中到当前开始时间
    const time = this.data.formData.qjkssj_time || '08:00';
    const [h, m] = time.split(':');
    this.setData({
      startTimeColumns: this.buildColumnsWithDefault(this.data.timeColumns, h, m),
      showStartTimePicker: true
    });
  },

  onStartTimePickerClose() {
    this.setData({ showStartTimePicker: false });
  },

  onStartTimeConfirm(e) {
    const { value } = e.detail;
    let hour = '08';
    let minute = '00';
    
    if (Array.isArray(value) && value.length >= 2) {
      hour = value[0].value || value[0] || '08';
      minute = value[1].value || value[1] || '00';
    }
    
    const time = `${hour}:${minute}`;
    
    // 计算结束时间默认值：开始时间+1小时
    const startH = parseInt(hour, 10);
    const startM = parseInt(minute, 10);
    let endH = startH + 1;
    let endM = startM;
    if (endH >= 24) endH = 23;
    const endHour = String(endH).padStart(2, '0');
    const endMinute = String(endM).padStart(2, '0');
    const endTime = `${endHour}:${endMinute}`;
    
    if (this.data.formData.qjkssj) {
      const datePart = this.data.formData.qjkssj.split(' ')[0];
      const newStartTime = `${datePart} ${time}:00`;
      
      // 同时更新结束时间
      const endDatePart = this.data.formData.qjjssj ? this.data.formData.qjjssj.split(' ')[0] : datePart;
      const newEndTime = `${endDatePart} ${endTime}:00`;
      
      this.setData({
        'formData.qjkssj': newStartTime,
        'formData.qjkssj_time': time,
        'formData.qjjssj': newEndTime,
        'formData.qjjssj_time': endTime,
        endTimeColumns: this.buildColumnsWithDefault(this.data.timeColumns, endHour, endMinute),
        showStartTimePicker: false
      });
      this.calcDuration();
    } else {
      this.setData({
        'formData.qjkssj_time': time,
        'formData.qjjssj_time': endTime,
        endTimeColumns: this.buildColumnsWithDefault(this.data.timeColumns, endHour, endMinute),
        showStartTimePicker: false
      });
    }
  },

  showEndTimePicker() {
    if (!this.data.formData.qjjssj) {
      this.showError('请先选择请假日期');
      return;
    }
    const time = this.data.formData.qjjssj_time || '18:00';
    const [h, m] = time.split(':');
    this.setData({
      endTimeColumns: this.buildColumnsWithDefault(this.data.timeColumns, h, m),
      showEndTimePicker: true
    });
  },

  onEndTimePickerClose() {
    this.setData({ showEndTimePicker: false });
  },

  onEndTimeConfirm(e) {
    const { value } = e.detail;
    let hour = '18';
    let minute = '00';
    
    if (Array.isArray(value) && value.length >= 2) {
      hour = value[0].value || value[0] || '18';
      minute = value[1].value || value[1] || '00';
    }
    
    const time = `${hour}:${minute}`;
    
    if (this.data.formData.qjjssj) {
      const datePart = this.data.formData.qjjssj.split(' ')[0];
      const newEndTime = `${datePart} ${time}:00`;
      
      // 检查结束时间是否晚于开始时间
      if (this.data.formData.qjkssj && newEndTime <= this.data.formData.qjkssj) {
        this.showError('结束时间必须晚于开始时间');
        return;
      }
      
      this.setData({
        'formData.qjjssj': newEndTime,
        'formData.qjjssj_time': time,
        showEndTimePicker: false
      });
      this.calcDuration();
    } else {
      this.setData({
        'formData.qjjssj_time': time,
        showEndTimePicker: false
      });
    }
  },

  // 显示日历选择器
  showDateRangePicker() {
    this.setData({ showCalendar: true });
  },

  onCalendarClose() {
    this.setData({ showCalendar: false });
  },

  onCalendarConfirm(e) {
    const dates = e.detail;
    
    if (!Array.isArray(dates) || dates.length !== 2) {
      this.showError('请选择完整的日期范围');
      return;
    }
    
    const [startDate, endDate] = dates;
    
    const diffDays = (endDate - startDate) / (1000 * 60 * 60 * 24);
    if (diffDays > 7) {
      this.showError('请假时长不能超过7天，超过7天请到班主任那里当面请假');
      return;
    }
    
    const startDateStr = this.formatDate(new Date(startDate));
    const endDateStr = this.formatDate(new Date(endDate));
    
    const startTime = this.data.formData.qjkssj_time || '08:00';
    const endTime = this.data.formData.qjjssj_time || '09:00';
    
    const qjkssj = `${startDateStr} ${startTime}:00`;
    const qjjssj = `${endDateStr} ${endTime}:00`;
    const dateRangeDisplay = `${startDateStr} 至 ${endDateStr}`;
    
    this.setData({
      'formData.qjkssj': qjkssj,
      'formData.qjjssj': qjjssj,
      'formData.qjkssj_time': startTime,
      'formData.qjjssj_time': endTime,
      selectedDateRange: [startDate, endDate],
      dateRangeDisplay: dateRangeDisplay,
      showCalendar: false
    });
    this.calcDuration();
  },

  // 计算并展示请假时长
  calcDuration() {
    const { qjkssj, qjjssj } = this.data.formData;
    if (!qjkssj || !qjjssj) {
      this.setData({ durationDisplay: '' });
      return;
    }
    const diffMs = new Date(qjjssj).getTime() - new Date(qjkssj).getTime();
    if (diffMs <= 0) {
      this.setData({ durationDisplay: '' });
      return;
    }
    const totalHours = diffMs / (1000 * 60 * 60);
    let durationDisplay = '';
    if (totalHours < 1) {
      durationDisplay = `${Math.round(totalHours * 60)}分钟`;
    } else if (totalHours <= 24) {
      durationDisplay = `${totalHours.toFixed(1)}小时`;
    } else {
      const days = Math.floor(totalHours / 24);
      const hours = totalHours % 24;
      durationDisplay = hours > 0 ? `${days}天${hours.toFixed(1)}小时` : `${days}天`;
    }
    this.setData({ durationDisplay });
  },

  formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  },

  togglePromise() {
    this.setData({ promised: !this.data.promised });
  },

  async submitForm() {
    const { formData, isEdit, leaveId } = this.data;

    if (!this.data.promised) { this.showError('请先勾选本人承诺'); return; }
    if (!formData.qjlb) { this.showError('请选择请假类别'); return; }
    if (!formData.qjsy || formData.qjsy.trim() === '') { this.showError('请填写请假事由'); return; }
    if (!formData.qjkssj) { this.showError('请选择请假开始时间'); return; }
    if (!formData.qjjssj) { this.showError('请选择请假结束时间'); return; }
    if (!formData.xslxxl || formData.xslxxl.trim() === '') { this.showError('请填写离校线路'); return; }
    if (!formData.xslxjtgj || formData.xslxjtgj.trim() === '') { this.showError('请填写离校交通工具'); return; }

    const startTime = new Date(formData.qjkssj).getTime();
    const endTime = new Date(formData.qjjssj).getTime();
    const diffDays = (endTime - startTime) / (1000 * 60 * 60 * 24);
    
    if (diffDays > 7) {
      this.showError('请假时长不能超过7天，超过7天请到班主任那里当面请假');
      return;
    }

    this.setData({ loading: true });

    try {
      if (isEdit) {
        await tokenRequest({
          url: `/student/leave/update/${leaveId}`,
          method: 'PUT',
          data: formData
        });
        this.showSuccess('修改请假申请成功');
      } else {
        await tokenPost('/student/leave/apply', formData);
        this.showSuccess('请假申请提交成功');
      }
      
      setTimeout(() => { wx.navigateBack(); }, 1500);
    } catch (error) {
      this.showError(isEdit ? '修改请假申请失败，请重试' : '提交请假申请失败，请重试');
    }

    this.setData({ loading: false });
  },

  goBack() {
    wx.navigateBack();
  }
}, {
  requireAuth: true
});
