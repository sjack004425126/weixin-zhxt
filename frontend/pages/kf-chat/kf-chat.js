const app = getApp();
const { createPage } = require('../../utils/page-mixin');
const { STATIC_IMAGES } = require('../../utils/static-images');
const { getUserToken, agentRequest, AGENT_API_BASE } = require('../../utils/agent-auth');

const AGENT_ID = 1000007;
const POLL_INTERVAL = 1000;
const POLL_MAX_ATTEMPTS = 60;

function pad2(n) { return n < 10 ? '0' + n : String(n); }

function formatTime(ts) {
  if (!ts) return '';
  var d = new Date(ts);
  if (isNaN(d.getTime())) return '';
  var now = new Date();
  var isToday = d.toDateString() === now.toDateString();
  if (isToday) return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
}

function createId() {
  return 'm_' + Date.now() + '_' + Math.random().toString(16).slice(2);
}

function getUserId() {
  var userInfo = app.globalData.userInfo || {};
  if (userInfo.xs_xh) return userInfo.xs_xh;
  var cachedId = wx.getStorageSync('kf_chat_user_id');
  if (cachedId) return cachedId;
  var newId = 'guest_' + Date.now();
  wx.setStorageSync('kf_chat_user_id', newId);
  return newId;
}

createPage({
  data: {
    defaultAvatar: STATIC_IMAGES.defaultAvatar,
    messages: [],
    inputValue: '',
    scrollIntoView: '',
    scrollTop: 0,
    inputFocus: false,
    isTyping: false,
    sending: false,
    initialized: false
  },

  onLoad: function() {
    this._userId = getUserId();
    this._conversationId = AGENT_ID + ':' + this._userId;
    this._maxMsgId = 0;
    this.setData({ messages: [] });
    this._initToken();
  },

  onUnload: function() {
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
  },

  _initToken: function() {
    var that = this;
    getUserToken(this._userId).then(function() {
      that.loadHistory();
    }).catch(function(e) {
      console.error('[Chat] Token init failed', e);
      that.showError('initialization failed, please retry');
    });
  },

  loadHistory: function() {
    var that = this;
    agentRequest(this._userId, {
      url: AGENT_API_BASE + '/agent/messages',
      method: 'GET',
      data: { conversation_id: this._conversationId, limit: 100 }
    }).then(function(res) {
      var rawMessages = res.messages || [];
      that._maxMsgId = rawMessages.reduce(function(max, m) {
        return (m.id || 0) > max ? (m.id || 0) : max;
      }, 0);
      that.setData({ initialized: true });
      if (!Array.isArray(rawMessages) || rawMessages.length === 0) return;
      var messages = rawMessages.map(function(m) {
        return that._toMsgItem(m);
      }).filter(Boolean);
      that.setData({ messages: messages }, function() { that._scrollToBottom(); });
    }).catch(function(e) {
      console.error('[Chat] load history failed', e);
      that.setData({ initialized: true });
    });
  },

  handleSend: function() {
    var text = String(this.data.inputValue || '').trim();
    if (!text || this.data.sending || !this.data.initialized) return;

    var userMsg = {
      id: createId(),
      direction: 'outgoing',
      text: text,
      ts: Date.now(),
      timeText: formatTime(Date.now())
    };
    var messages = this.data.messages.concat([userMsg]);
    var that = this;

    this.setData({
      messages: messages,
      inputValue: '',
      inputFocus: false,
      sending: true,
      isTyping: true
    }, function() { that._scrollToBottom(); });

    agentRequest(this._userId, {
      url: AGENT_API_BASE + '/agent/callback',
      method: 'POST',
      data: {
        user_id: this._userId,
        agent_id: AGENT_ID,
        content: text
      }
    }).then(function(res) {
      if (res && res.success) {
        that._pollForReply(0);
      } else {
        that.setData({ isTyping: false, sending: false });
        that.showError((res && res.message) || 'send failed');
      }
    }).catch(function(e) {
      that.setData({ isTyping: false, sending: false });
      that.showError('network error, please retry');
    });
  },

  _toMsgItem: function(m) {
    if (!m.content) return null;
    var isIncoming = (m.role === 'assistant' || m.is_ai === true || m.is_ai === 1);
    var item = {
      id: String(m.id || createId()),
      direction: isIncoming ? 'incoming' : 'outgoing',
      text: m.content,
      ts: m.created_at || Date.now(),
      timeText: formatTime(m.created_at)
    };
    return item;
  },

  _pollForReply: function(attempts) {
    if (attempts >= POLL_MAX_ATTEMPTS) {
      this.setData({ isTyping: false, sending: false });
      this.showError('AI response timeout');
      return;
    }

    var that = this;
    this._pollTimer = setTimeout(function() {
      console.log('[Poll] attempt=' + attempts + ' after_id=' + that._maxMsgId);
      agentRequest(that._userId, {
        url: AGENT_API_BASE + '/agent/messages',
        method: 'GET',
        data: {
          conversation_id: that._conversationId,
          after_id: that._maxMsgId,
          limit: 10
        }
      }).then(function(res) {
        console.log('[Poll] 返回', (res.messages || []).length, '条, total=', res.total);
        var newMessages = res.messages || [];
        if (!newMessages.length) {
          that._pollForReply(attempts + 1);
          return;
        }

        newMessages.forEach(function(m) {
          if ((m.id || 0) > that._maxMsgId) that._maxMsgId = m.id;
        });

        var aiMessages = newMessages.filter(function(m) {
          return m.role === 'assistant' || m.is_ai === true || m.is_ai === 1;
        });
        var hasAiReply = aiMessages.length > 0;

        if (hasAiReply) {
          var items = aiMessages.map(function(m) { return that._toMsgItem(m); }).filter(Boolean);
          var updated = that.data.messages.concat(items);
          that.setData({
            messages: updated,
            isTyping: false,
            sending: false
          }, function() { that._scrollToBottom(); });
        } else {
          that._pollForReply(attempts + 1);
        }
      }).catch(function() {
        that._pollForReply(attempts + 1);
      });
    }, POLL_INTERVAL);
  },

  handleInputChange: function(e) {
    this.setData({ inputValue: e.detail.value });
  },

  handleInputBlur: function() {
    this.setData({ inputFocus: false });
  },

  goBack: function() {
    wx.navigateBack({ delta: 1, fail: function() { wx.switchTab({ url: '/pages/home/home' }); } });
  },

  scrollToTop: function() {
    this.setData({ scrollTop: this.data.scrollTop === 0 ? 0.1 : 0 });
  },

  scrollToBottom: function() {
    this._bottomVal = (this._bottomVal || 99999) + 1;
    this.setData({ scrollTop: this._bottomVal });
  },

  _scrollToBottom: function() {
    this._bottomVal = (this._bottomVal || 99999) + 1;
    this.setData({ scrollTop: this._bottomVal });
  }
}, {
  requireAuth: true,
  userType: null // 共享页面，遍历所有存储恢复
});
