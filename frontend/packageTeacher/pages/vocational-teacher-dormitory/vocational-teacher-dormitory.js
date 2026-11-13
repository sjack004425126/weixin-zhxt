const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    // 主页面：学生列表
    studentList: [],
    filteredList: [],
    groupedList: [],
    loading: true,
    selectedClassId: '',
    classOptions: [],
    classList: [],
    filterType: 'all',
    filterOptions: [
      { text: '全部', value: 'all' },
      { text: '已分配', value: 'assigned' },
      { text: '未分配', value: 'unassigned' }
    ],
    total: 0,
    assigned: 0,
    unassigned: 0,
    // 前端搜索（按姓名/学号/宿舍号）
    searchKeyword: '',
    // 弹窗
    showAssignPopup: false,
    currentStudent: {},
    buildings: [],
    popupBuilding: null,
    popupFloors: [],
    popupFloor: null,
    popupRooms: [],
    leftRooms: [],
    rightRooms: [],
    popupCurrentRoom: null,
    bedRows: [],
    bedLoading: false,
    selectedBed: null,
    assigning: false
  },

  onLoad() {
    this.loadClassList();
  },

  // ========== 主页面：学生列表 ==========
  async loadClassList() {
    try {
      const res = await tokenGet('/vocational_teacher/classes');
      const classList = res || [];
      const classOptions = classList.map(c => ({ text: c.name, value: c.id }));
      this.setData({
        classList, classOptions,
        selectedClassId: classList.length > 0 ? classList[0].id : ''
      });
      if (classList.length > 0) this.loadStudentList();
      else this.setData({ loading: false });
    } catch (e) {
      this.setData({ loading: false });
      this.showError('获取班级列表失败');
    }
  },

  onClassChange(e) {
    this.setData({ selectedClassId: e.detail });
    this.loadStudentList();
  },

  onFilterChange(e) {
    this.setData({ filterType: e.detail });
    this.applyFilter();
  },

  // 搜索输入（仅前端过滤）
  onSearchInput(e) {
    this.setData({ searchKeyword: e.detail.value });
    this.applyFilter();
  },

  // 清空搜索
  onSearchClear() {
    this.setData({ searchKeyword: '' });
    this.applyFilter();
  },

  applyFilter() {
    const { filterType, studentList, searchKeyword } = this.data;
    // 1. 按状态过滤（已分配/未分配）
    let filtered = studentList;
    if (filterType === 'assigned') filtered = filtered.filter(s => s.dorm_info);
    else if (filterType === 'unassigned') filtered = filtered.filter(s => !s.dorm_info);

    // 2. 按搜索关键字过滤（姓名/学号/宿舍号/楼栋）
    const kw = (searchKeyword || '').trim();
    if (kw) {
      const lower = kw.toLowerCase();
      filtered = filtered.filter(s => {
        // 姓名
        if (s.xm && s.xm.includes(kw)) return true;
        // 学号
        if (s.xh && String(s.xh).includes(kw)) return true;
        // 宿舍信息（楼栋/楼层/室号/床号）
        if (s.dorm_info) {
          const d = s.dorm_info;
          if ((d.ld_mc && d.ld_mc.includes(kw)) ||
              (d.ssh && d.ssh.includes(kw)) ||
              (d.lc != null && String(d.lc).includes(kw)) ||
              (d.cwh != null && String(d.cwh).includes(kw)) ||
              (d.full_name && d.full_name.includes(kw))) return true;
        }
        // 拼音首字母（如果有）
        if (s.pinyin_initial && s.pinyin_initial.toLowerCase().includes(lower)) return true;
        return false;
      });
    }

    // 3. 给每个学生预计算性别对应的英文类名
    filtered.forEach(s => {
      s.genderClass = s.xb === '男' ? 'male' : (s.xb === '女' ? 'female' : '');
    });
    this.setData({ filteredList: filtered, groupedList: this.groupByRoom(filtered) });
  },

  groupByRoom(students) {
    // 未分配宿舍的单独一组，已分配的按宿舍号分组
    const roomMap = {};
    const roomOrder = [];
    const unassigned = [];

    students.forEach(s => {
      if (!s.dorm_info) {
        unassigned.push(s);
      } else {
        const key = s.dorm_info.ss_id;
        if (!roomMap[key]) {
          roomMap[key] = { ss_label: s.dorm_info.ss_label, students: [] };
          roomOrder.push(key);
        }
        roomMap[key].students.push(s);
      }
    });

    const groups = roomOrder.map(k => roomMap[k]);
    if (unassigned.length > 0) {
      groups.push({ ss_label: '未分配宿舍', students: unassigned });
    }
    return groups;
  },

  async loadStudentList() {
    if (!this.data.selectedClassId) {
      this.setData({ studentList: [], filteredList: [], loading: false, total: 0, assigned: 0, unassigned: 0 });
      return;
    }
    this.setData({ loading: true });
    try {
      const res = await tokenGet('/dormitory/class_dormitory', { bj_id: this.data.selectedClassId });
      const data = res || {};
      this.setData({
        studentList: data.students || [],
        total: data.total || 0,
        assigned: data.assigned || 0,
        unassigned: data.unassigned || 0,
        loading: false,
        filterType: 'all'
      });
      this.applyFilter();
    } catch (e) {
      this.setData({ loading: false });
      this.showError('获取住宿数据失败');
    }
  },

  // ========== 弹窗：分配宿舍 ==========
  onEditTap(e) {
    const student = e.currentTarget.dataset.student;
    this.setData({
      currentStudent: student,
      showAssignPopup: true,
      popupBuilding: null,
      popupFloors: [],
      popupFloor: null,
      popupRooms: [], leftRooms: [], rightRooms: [],
      popupCurrentRoom: null,
      bedRows: [],
      selectedBed: null
    });
    this.loadBuildings();
  },

  onClosePopup() {
    this.setData({ showAssignPopup: false });
  },

  async loadBuildings() {
    try {
      const res = await tokenGet('/dormitory/buildings');
      this.setData({ buildings: res || [] });
    } catch (e) {
      this.showError('获取楼栋失败');
    }
  },

  async onSelectBuilding(e) {
    const id = e.currentTarget.dataset.id;
    this.setData({
      popupBuilding: id,
      popupFloor: null, popupFloors: [],
      popupRooms: [], popupCurrentRoom: null,
      bedRows: [], selectedBed: null
    });
    try {
      const res = await tokenGet('/dormitory/floors', { ld_id: id });
      this.setData({ popupFloors: res || [] });
    } catch (e) {
      this.showError('获取楼层失败');
    }
  },

  async onSelectFloor(e) {
    const id = e.currentTarget.dataset.id;
    this.setData({
      popupFloor: id,
      popupRooms: [], leftRooms: [], rightRooms: [],
      popupCurrentRoom: null, bedRows: [], selectedBed: null
    });
    try {
      const res = await tokenGet('/dormitory/rooms', { lc_id: id });
      const rooms = res || [];
      // 给每个宿舍加序号
      rooms.forEach((r, i) => { r._idx = i + 1; });
      this.setData({ popupRooms: rooms });
      this.buildCorridorLayout(rooms);
    } catch (e) {
      this.showError('获取宿舍失败');
    }
  },

  // 构建走廊两侧布局：左右交替分配，槽位数按房间总数动态计算
  // 房间较多时左右仍保持等高，wxss 沿用单走廊样式即可自适应纵向延展
  buildCorridorLayout(rooms) {
    // 一侧需要的槽位数 = ceil(rooms.length / 2)；最少 10 保证无房间时走廊完整
    const slotsPerSide = Math.max(10, Math.ceil(rooms.length / 2));
    const left = new Array(slotsPerSide).fill(null);
    const right = new Array(slotsPerSide).fill(null);
    // 偶数索引放左侧，奇数索引放右侧，逐行配对
    rooms.forEach((room, i) => {
      const side = i % 2 === 0 ? left : right;
      const idx = Math.floor(i / 2);
      side[idx] = room;  // 槽位已动态扩到能容纳全部房间
    });
    this.setData({ leftRooms: left, rightRooms: right });
  },

  async onSelectRoom(e) {
    const room = e.currentTarget.dataset.room;
    // 立即设置房间（不带 beds），进入加载状态
    this.setData({
      popupCurrentRoom: { ...room, beds: [] },
      selectedBed: null,
      bedRows: [],
      bedLoading: true
    });
    try {
      const res = await tokenGet('/dormitory/room/beds', { ss_id: room.id });
      if (res && res.beds) {
        this.setData({
          popupCurrentRoom: { ...room, beds: res.beds },
          bedRows: [],
          bedLoading: false
        });
        this.buildBedRows(res.beds);
      } else {
        this.setData({ bedLoading: false });
        this.showError('该宿舍暂无床位');
      }
    } catch (err) {
      this.setData({ bedLoading: false });
      this.showError('获取床位失败');
    }
  },

  onBackToRooms() {
    this.setData({ popupCurrentRoom: null, bedRows: [], selectedBed: null });
    // 刷新宿舍列表
    if (this.data.popupFloor) {
      this.onSelectFloor({ currentTarget: { dataset: { id: this.data.popupFloor } } });
    }
  },

  buildBedRows(beds) {
    // 按宿舍物理布局排列床位
    // 6人间：左列[3,2,1]，右列[4,5,6]
    // 8人间：左列[3,2,7,1]，右列[4,5,8,6]
    // 规则：按床位号建立映射，再按固定顺序排列
    const bedMap = {};
    beds.forEach(b => { bedMap[parseInt(b.cwh)] = b; });
    const total = beds.length;

    let leftOrder, rightOrder;
    if (total <= 6) {
      // 6人间及以下：左列 3→2→1，右列 4→5→6
      leftOrder = [3, 2, 1];
      rightOrder = [4, 5, 6];
    } else {
      // 8人间：左列 3→2→7→1，右列 4→5→8→6
      leftOrder = [3, 2, 7, 1];
      rightOrder = [4, 5, 8, 6];
    }

    // 过滤掉不存在的床位号
    const leftBeds = leftOrder.map(n => bedMap[n] || null);
    const rightBeds = rightOrder.map(n => bedMap[n] || null);

    const rows = [];
    const rowCount = Math.max(leftBeds.length, rightBeds.length);
    for (let i = 0; i < rowCount; i++) {
      rows.push({
        left: leftBeds[i] || null,
        right: rightBeds[i] || null
      });
    }
    this.setData({ bedRows: rows });
  },

  // 点击空闲床位 → 直接分配
  onPickBed(e) {
    const bedId = e.currentTarget.dataset.bedId;
    if (!bedId) return;
    const { currentStudent } = this.data;
    
    // 如果学生已有床位，提示会自动更换
    let msg = `确定将 ${currentStudent.xm} 分配到此床位吗？`;
    if (currentStudent.dorm_info) {
      msg = `${currentStudent.xm} 当前在「${currentStudent.dorm_info.full_name}」，确定更换到此床位吗？（旧床位会自动释放）`;
    }
    
    wx.showModal({
      title: '确认分配',
      content: msg,
      success: async (res) => {
        if (res.confirm) {
          this.doAssign(bedId);
        }
      }
    });
  },

  async doAssign(bedId) {
    this.setData({ assigning: true });
    try {
      await tokenPost('/dormitory/assign', {
        student_id: this.data.currentStudent.id,
        cw_id: bedId
      });
      this.showSuccess('分配成功');
      this.setData({ showAssignPopup: false, assigning: false });
      this.loadStudentList();
    } catch (e) {
      this.setData({ assigning: false });
      this.showError(e.message || '分配失败');
    }
  },

  async onClearDorm() {
    const { currentStudent } = this.data;
    wx.showModal({
      title: '提示',
      content: `确定取消 ${currentStudent.xm} 的宿舍分配吗？`,
      success: async (res) => {
        if (res.confirm) {
          try {
            await tokenPost('/dormitory/assign', {
              student_id: currentStudent.id,
              cw_id: null
            });
            this.showSuccess('已取消分配');
            this.setData({ showAssignPopup: false });
            this.loadStudentList();
          } catch (e) {
            this.showError(e.message || '操作失败');
          }
        }
      }
    });
  },

  callStudent(e) {
    const { phone, name } = e.currentTarget.dataset;
    if (!phone) { this.showError(`${name}暂无联系电话`); return; }
    wx.makePhoneCall({ phoneNumber: phone });
  },

  onCallPhone(e) {
    const phone = e.currentTarget.dataset.phone;
    if (!phone) return;
    wx.makePhoneCall({ phoneNumber: String(phone) });
  },

  goBack() {
    wx.navigateBack();
  }
}, {
  requireAuth: true,
  userType: 'vocational_teacher'
});