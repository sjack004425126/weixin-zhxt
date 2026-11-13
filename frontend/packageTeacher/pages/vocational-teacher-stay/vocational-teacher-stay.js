const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { resolveImageUrl } = require('../../../utils/image-url');

createPage({
  data: {
    studentList: [],
    filteredList: [],
    groupedList: [],
    loading: true,
    statusFilter: 'all',
    statusOptions: [
      { text: '全部', value: 'all' },
      { text: '待审批', value: '0' },
      { text: '已批准', value: '1' },
      { text: '已拒绝', value: '2' }
    ],
    statusMap: { 0: '待审批', 1: '已批准', 2: '已拒绝', 3: '已过期', 4: '已取消' },
    showDetail: false,
    currentStudent: null,
    approveRemark: '',
    approving: false
  },

  onLoad() { this.loadStudents(); },

  onStatusChange(e) {
    this.setData({ statusFilter: e.detail });
    this.applyFilter();
  },

  applyFilter() {
    const { statusFilter, studentList } = this.data;
    let filtered = studentList;
    if (statusFilter !== 'all') {
      const st = parseInt(statusFilter);
      filtered = studentList.filter(s => s.stay && s.stay.status === st);
    }
    // 按班级分组
    const groups = this.groupByClass(filtered);
    this.setData({ filteredList: filtered, groupedList: groups });
  },

  groupByClass(students) {
    const map = {};
    const order = [];
    students.forEach(s => {
      const key = s.bj_id || 0;
      if (!map[key]) {
        map[key] = { bj_mc: s.bj_mc || '未分配班级', students: [] };
        order.push(key);
      }
      map[key].students.push(s);
    });
    return order.map(k => map[k]);
  },

  async loadStudents() {
    this.setData({ loading: true });
    try {
      const res = await tokenGet('/vocational_teacher/stay/class_list');
      const rawList = (res && res.students) || [];
      // 后端 photo_url 为相对路径，统一拼 BASE_URL
      const studentList = rawList.map(s => ({
        ...s,
        photo_url: s.photo_url ? resolveImageUrl(s.photo_url) : ''
      }));
      this.setData({ studentList, loading: false });
      this.applyFilter();
    } catch (e) {
      this.setData({ loading: false });
      this.showError('获取数据失败');
    }
  },

  onStayTap(e) {
    const student = e.currentTarget.dataset.student;
    if (!student.stay) return;
    this.setData({ showDetail: true, currentStudent: student, approveRemark: '' });
  },

  closeDetail() { this.setData({ showDetail: false }); },
  onRemarkChange(e) { this.setData({ approveRemark: e.detail }); },

  async approvePass() { await this.doApprove(1); },
  async approveReject() { await this.doApprove(2); },

  async doApprove(status) {
    this.setData({ approving: true });
    try {
      await tokenPost('/vocational_teacher/stay/approve', {
        stay_id: this.data.currentStudent.stay.id,
        status: status,
        remark: this.data.approveRemark
      });
      this.showSuccess(status === 1 ? '已批准' : '已拒绝');
      this.setData({ showDetail: false, approving: false });
      this.loadStudents();
    } catch (e) {
      this.setData({ approving: false });
      this.showError(e.message || '审批失败');
    }
  },

  callStudent(e) {
    const { phone, name } = e.currentTarget.dataset;
    if (!phone) { this.showError(`${name}暂无联系电话`); return; }
    wx.makePhoneCall({ phoneNumber: phone });
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'vocational_teacher'
});
