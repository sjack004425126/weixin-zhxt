# 更简洁的请求写法

## 1. 原有参数完全支持

```javascript
// 这些写法都完全支持，没有任何变化
const { post, get } = require('../../utils/request');

// 带loading提示
const result = await post('/api/test', { data: 'value' }, {
  loadingTitle: '获取报名专业信息中...'
});

// 不显示错误提示
const result = await post('/api/test', { data: 'value' }, {
  showError: false,
  loadingTitle: '处理中...'
});

// 自定义超时
const result = await post('/api/test', { data: 'value' }, {
  timeout: 10000,
  loadingTitle: '数据同步中...'
});
```

## 2. 新增预设配置

```javascript
const { post, silentPost, quickPost, PRESETS } = require('../../utils/request');

// 静默请求（不显示loading和错误）
const result = await silentPost('/api/background-sync', { data: 'value' });

// 快速请求（5秒超时）
const result = await quickPost('/api/quick-check', { data: 'value' });

// 使用预设 + 自定义配置
const result = await post('/api/test', { data: 'value' }, {
  ...PRESETS.important,  // 重要操作预设
  onBusinessError: (data, msg) => this.handleError(data)
});
```

## 3. 简化回调写法

### 原写法
```javascript
const result = await post('/api/submit', formData, {
  loadingTitle: '提交中...',
  onBusinessError: function(responseData, errorMsg) {
    console.log('业务错误详情:', responseData);
    if (responseData.code === 'VALIDATION_ERROR') {
      this.showValidationErrors(responseData.data.errors);
    }
  },
  onNetworkError: function(err, errorMsg) {
    console.log('网络错误:', err);
    this.showRetryDialog();
  }
});
```

### 简化写法
```javascript
const result = await post('/api/submit', formData, {
  loadingTitle: '提交中...',
  onBusinessError: (data, msg) => {
    if (data.code === 'VALIDATION_ERROR') {
      this.showValidationErrors(data.data.errors);
    }
  },
  onNetworkError: () => this.showRetryDialog()
});
```

## 4. 预定义错误处理器

```javascript
// 在页面中定义通用错误处理器
const commonErrorHandlers = {
  validation: (data) => this.showValidationErrors(data.data.errors),
  permission: () => wx.redirectTo({ url: '/pages/login/login' }),
  retry: () => this.showRetryDialog()
};

// 使用时更简洁
const result = await post('/api/submit', formData, {
  loadingTitle: '提交中...',
  onBusinessError: (data) => {
    if (data.code === 'VALIDATION_ERROR') commonErrorHandlers.validation(data);
    if (data.code === 'PERMISSION_DENIED') commonErrorHandlers.permission();
  },
  onNetworkError: commonErrorHandlers.retry
});
```

## 5. 实际使用对比

### 表单提交场景

**传统写法（仍然支持）：**
```javascript
try {
  wx.showLoading({ title: '提交中...' });
  const result = await post('/api/submit', this.data.formData);
  wx.hideLoading();
  wx.showToast({ title: '提交成功', icon: 'success' });
  wx.navigateBack();
} catch (error) {
  wx.hideLoading();
  wx.showToast({ title: error.msg || '提交失败', icon: 'none' });
  if (error.code === 'VALIDATION_ERROR') {
    this.showValidationErrors(error.data.errors);
  }
}
```

**新的简化写法：**
```javascript
try {
  const result = await post('/api/submit', this.data.formData, {
    loadingTitle: '提交中...',
    onBusinessError: (data) => {
      if (data.code === 'VALIDATION_ERROR') {
        this.showValidationErrors(data.data.errors);
      }
    }
  });
  
  this.showSuccess('提交成功');
  wx.navigateBack();
} catch (error) {
  // 错误已经自动处理和显示了
  console.log('提交失败:', error);
}
```

## 6. 可用的预设配置

```javascript
const { PRESETS } = require('../../utils/request');

// PRESETS.silent - 静默请求
{ showLoading: false, showError: false }

// PRESETS.quick - 快速请求  
{ timeout: 5000, loadingTitle: '请稍候...' }

// PRESETS.upload - 上传配置
{ timeout: 30000, loadingTitle: '上传中...' }

// PRESETS.important - 重要操作
{ timeout: 30000, loadingTitle: '处理中，请稍候...' }
```

## 总结

✅ **向后兼容** - 所有原有写法都支持  
✅ **更简洁** - 提供预设配置和便捷方法  
✅ **更灵活** - 可以组合使用预设和自定义配置  
✅ **更安全** - 错误处理更完善  

选择适合您的写法即可，从简单的 `loadingTitle` 到复杂的错误处理回调，都完全支持！
