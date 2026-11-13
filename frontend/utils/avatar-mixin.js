/**
 * 个人中心头像混入（4 个页面共用）
 *
 * 使用方式：
 *   const { createPage } = require('../../../utils/page-mixin');
 *   const { avatarMixin, avatarMixinData } = require('../../../utils/avatar-mixin');
 *
 *   createPage({
 *     ...avatarMixin,
 *     data: { ...avatarMixinData(), ...其他字段 },
 *     onShow() { this.loadAvatar(); }
 *   })
 *
 * 行为：
 *   - 页面显示时拉取 /photo/my_avatar，展示真实头像
 *   - 没有头像时弹出"请上传头像"提示（引导去上传）
 *   - 点击头像：已有头像 → 预览；无头像 → 引导上传
 *   - 上传走后端一体化流水线（抠图 + 美颜 + MinIO + 海康同步）
 */
const { tokenGet } = require('./request');
const { resolveImageUrl } = require('./image-url');
const { chooseAndUploadAvatar } = require('./avatar-upload');

/** 页面 data 中需要声明的字段 */
function avatarMixinData() {
  return {
    // 真实头像地址（空字符串表示没有）
    avatarUrl: '',
    // 是否已有头像
    hasAvatar: false,
    // "请上传头像"提示条是否显示
    showAvatarTip: false,
    // 上传处理中遮罩
    avatarOverlay: {
      show: false,
      title: '头像处理中',
      step: '',
      progress: -1,
      tip: '请稍候，预计需要 10-60 秒',
    },
  };
}

const avatarMixin = {
  /**
   * 拉取当前用户头像状态。
   */
  async loadAvatar() {
    try {
      const res = await tokenGet('/photo/my_avatar', {}, { showLoading: false });
      if (!res) return;

      const hasAvatar = !!res.has_photo;
      const avatarUrl = hasAvatar && res.photo_url ? resolveImageUrl(res.photo_url) : '';

      this.setData({
        hasAvatar,
        avatarUrl,
        showAvatarTip: !hasAvatar,
      });
    } catch (e) {
      console.warn('[avatar-mixin] 查询头像失败', e);
    }
  },

  /**
   * 点击头像：有头像 → 预览；无头像 → 引导上传。
   */
  onAvatarTap() {
    if (this.data.avatarUrl) {
      this.previewAvatar();
      return;
    }
    this.promptUploadAvatar();
  },

  /**
   * 无头像时提示用户上传。
   */
  promptUploadAvatar() {
    wx.showModal({
      title: '还没有头像',
      content: '上传头像后将自动完成抠图、美化并同步到海康，是否现在上传？',
      confirmText: '去上传',
      cancelText: '稍后',
      success: (res) => {
        if (res.confirm) {
          this.chooseAvatarSource();
        }
      },
    });
  },

  /**
   * 选择拍照 / 相册。
   */
  chooseAvatarSource() {
    wx.showActionSheet({
      itemList: ['拍照上传', '从相册选择'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this.doUploadAvatar(['camera']);
        } else if (res.tapIndex === 1) {
          this.doUploadAvatar(['album']);
        }
      },
      fail: () => {},
    });
  },

  /**
   * 执行上传（含抠图/美化/海康同步）。
   */
  async doUploadAvatar(sourceType) {
    this.setData({
      'avatarOverlay.show': true,
      'avatarOverlay.title': '头像处理中',
      'avatarOverlay.step': '正在上传照片...',
      'avatarOverlay.progress': 5,
      'avatarOverlay.tip': '请稍候，预计需要 10-60 秒',
    });

    try {
      const result = await chooseAndUploadAvatar({
        sourceType,
        onProgress: (info) => {
          if (info && typeof info.progress === 'number') {
            this.setData({
              'avatarOverlay.step': info.step || '',
              'avatarOverlay.progress': info.progress,
            });
          }
        },
      });

      const photoUrl = result && result.photo_url ? resolveImageUrl(result.photo_url) : '';
      this.setData({
        hasAvatar: !!photoUrl,
        avatarUrl: photoUrl,
        showAvatarTip: !photoUrl,
        'avatarOverlay.title': '上传成功',
        'avatarOverlay.step': '头像已上传并同步海康',
        'avatarOverlay.progress': 100,
        'avatarOverlay.tip': '点击任意位置关闭',
      });

      setTimeout(() => {
        this.setData({ 'avatarOverlay.show': false });
        this.showSuccess('头像上传成功');
      }, 1200);
    } catch (err) {
      this.setData({ 'avatarOverlay.show': false });
      // 用户主动取消选图，不报错
      if (err && err.cancelled) return;
      this.showError(this._avatarErrMsg(err));
    }
  },

  /**
   * 预览大图。
   */
  previewAvatar() {
    const url = this.data.avatarUrl;
    if (url) {
      wx.previewImage({ current: url, urls: [url] });
    }
  },

  /**
   * 头像 <image> 加载失败兜底：切回默认头像，避免一直裂图。
   * WXML 用法：<image src="{{avatarUrl || defaultAvatar}}" binderror="onAvatarError">
   */
  onAvatarError() {
    if (this.data.avatarUrl) {
      this.setData({ avatarUrl: '', hasAvatar: false, showAvatarTip: true });
    }
  },

  /**
   * 关闭处理中遮罩（点击遮罩时调用）。
   */
  closeAvatarOverlay() {
    if (this.data.avatarOverlay.show && this.data.avatarOverlay.progress < 100) {
      return; // 处理中不允许关闭
    }
    this.setData({ 'avatarOverlay.show': false });
  },

  _avatarErrMsg(err) {
    if (!err) return '操作失败';
    if (err.noToken || err.unauthorized) {
      return '登录已过期,请重新登录';
    }
    return err.msg || err.errorMsg || (err.responseData && err.responseData.msg) || err.message || '操作失败';
  },
};

module.exports = { avatarMixin, avatarMixinData };
