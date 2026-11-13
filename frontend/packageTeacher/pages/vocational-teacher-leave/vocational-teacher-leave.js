const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { resolveImageUrl } = require('../../../utils/image-url');

// 兜底用：当后端没有返回 duration_text 时，前端按开始/结束时间自己计算。
// 形如 "2天3小时" / "5小时30分" / "45分钟"。
function computeLeaveDuration(qjkssj, qjjssj) {
  if (!qjkssj || !qjjssj) return '';
  const kssj = new Date(qjkssj.replace(/-/g, '/'));
  const jssj = new Date(qjjssj.replace(/-/g, '/'));
  const ms = jssj.getTime() - kssj.getTime();
  if (isNaN(ms) || ms < 0) return '';
  const totalMinutes = Math.floor(ms / 60000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  const parts = [];
  if (days > 0) parts.push(days + '天');
  if (hours > 0) parts.push(hours + '小时');
  if (!parts) {
    if (minutes > 0) parts.push(minutes + '分钟');
    else parts.push('0分钟');
  }
  return parts.join('');
}

createPage({
  data: {
    activeTab: 0,
    leaveList: [],
    loading: true,
    statusFilter: 'pending',
    approveMode: 'bzr',
    isXsk: false,
    // 分页
    page: 1,
    pageSize: 10,
    total: 0,
    loadingMore: false,
    noMore: false
  },

  onLoad() {
    const app = getApp();
    const cached = wx.getStorageSync('vocational_teacher_auth_cache') || {};
    const userInfo = (app.globalData && app.globalData.userInfo) || cached.userInfo || {};
    const isXsk = userInfo.is_xsk || false;
    this.setData({ isXsk });
    this.loadLeaveList();
  },

  onShow() {
    // 仅从详情/审批页返回时刷新；图片预览关闭不触发刷新
    const pages = getCurrentPages();
    const prev = pages[pages.length - 2];
    if (prev && prev.route && prev.route.includes('leave-detail')) {
      this.resetAndLoad();
    }
  },

  onReachBottom() {
    if (!this.data.noMore && !this.data.loadingMore) {
      this.loadMore();
    }
  },

  onModeChange(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ approveMode: mode, activeTab: 0, statusFilter: 'pending' });
    this.resetAndLoad();
  },

  onTabChange(e) {
    const index = e.detail.index;
    const statusMap = ['pending', 'approved', 'rejected'];
    this.setData({ activeTab: index, statusFilter: statusMap[index] });
    this.resetAndLoad();
  },

  resetAndLoad() {
    this.setData({ page: 1, leaveList: [], noMore: false, total: 0 });
    this.loadLeaveList();
  },

  async loadLeaveList() {
    this.setData({ loading: this.data.page === 1 });

    try {
      const url = this.data.approveMode === 'xsk'
        ? '/vocational_teacher/leave/xsk_list'
        : '/vocational_teacher/leave/list';
      const res = await tokenGet(url, {
        status: this.data.statusFilter,
        page: this.data.page,
        page_size: this.data.pageSize
      });

      const list = res.list || [];
      const total = res.total || 0;
      // 补全 photo_url（拼 BASE_URL）和 duration_text（兜底）
      const enriched = list.map((it) => ({
        ...it,
        photo_url: it.photo_url ? resolveImageUrl(it.photo_url) : '',
        // 后端已返回 duration_text 时优先用；缺失时前端用开始/结束时间自己算
        duration_text: it.duration_text || computeLeaveDuration(it.qjkssj, it.qjjssj),
      }));
      const currentList = this.data.page === 1 ? enriched : this.data.leaveList.concat(enriched);

      this.setData({
        leaveList: currentList,
        total: total,
        loading: false,
        loadingMore: false,
        noMore: currentList.length >= total
      });
    } catch (error) {
      this.setData({ loading: false, loadingMore: false });
      this.showError('获取请假列表失败，请重试');
    }
  },

  loadMore() {
    this.setData({
      page: this.data.page + 1,
      loadingMore: true
    });
    this.loadLeaveList();
  },

  goToDetail(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/vocational-teacher-leave-detail/vocational-teacher-leave-detail?id=${id}`
    });
  },

  async handleApprove(e) {
    const { id } = e.currentTarget.dataset;
    const isXsk = this.data.approveMode === 'xsk';

    wx.showModal({
      title: isXsk ? '学生科审批' : '班主任审批',
      content: '确定通过该请假申请吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            const url = isXsk
              ? '/vocational_teacher/leave/xsk_approve'
              : '/vocational_teacher/leave/approve';
            const res = await tokenPost(url, { leave_id: id, status: 1 });
            this.showSuccess(res.msg)
            this.resetAndLoad();
          } catch (error) {
            this.showError('审批失败，请重试');
          }
        }
      }
    });
  },

  async handleReject(e) {
    const { id } = e.currentTarget.dataset;
    const isXsk = this.data.approveMode === 'xsk';

    wx.showModal({
      title: isXsk ? '学生科审批' : '班主任审批',
      content: '确定拒绝该请假申请吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            const url = isXsk
              ? '/vocational_teacher/leave/xsk_approve'
              : '/vocational_teacher/leave/approve';
            await tokenPost(url, { leave_id: id, status: 2 });
            this.showSuccess('已拒绝');
            this.resetAndLoad();
          } catch (error) {
            this.showError('操作失败，请重试');
          }
        }
      }
    });
  },

  async handleTeacherCancel(e) {
    const { id, xm } = e.currentTarget.dataset;

    wx.showModal({
      title: '代销假确认',
      content: `确定为学生${xm}代销假吗？`,
      success: async (res) => {
        if (res.confirm) {
          try {
            await tokenPost('/vocational_teacher/leave/teacher_cancel', { leave_id: id });
            this.showSuccess('代销假成功');
            this.resetAndLoad();
          } catch (error) {
            this.showError('代销假失败，请重试');
          }
        }
      }
    });
  },

  stopPropagation() {},

  /**
   * 点击头像 → 全屏预览照片（微信原生 wx.previewImage 自带双指缩放 / 左右切换 / 长按菜单）。
   * 无照片时仅占位，不触发预览。
   */
  onPhotoTap(e) {
    const { url, name } = e.currentTarget.dataset
    if (!url) return
    wx.previewImage({
      current: url,
      urls: [url],
      // 失败/长按保存等场景 wx 会自动处理；这里只用 showmenu 让用户能保存到相册
      showmenu: true,
    })
  },

  /**
   * 头像加载失败时，置空对应 item 的 photo_url，
   * 让模板回退到姓名首字母占位（避免破图影响观感）。
   */
  onPhotoError(e) {
    const idx = e.currentTarget.dataset.idx
    const list = this.data.leaveList
    if (typeof idx !== 'number' || !list[idx]) return
    // 复制新数组触发响应式更新
    const next = list.slice()
    next[idx] = { ...next[idx], photo_url: '' }
    this.setData({ leaveList: next })
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'vocational_teacher'
});