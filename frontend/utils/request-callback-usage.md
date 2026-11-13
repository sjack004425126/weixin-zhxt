# 请求自定义回调使用指南

现在 `request.js` 支持在保留默认错误处理的同时，添加自定义回调处理。

## 支持的自定义回调

### 1. `onBusinessError` - 业务错误回调
当后端返回 `{success: false}` 时触发

### 2. `onNetworkError` - 网络错误回调  
当网络请求失败时触发

## 使用方式

### 基础用法（保持原有功能）
```javascript
const { post } = require('../../utils/request');

// 默认行为：自动显示错误提示
const result = await post('/api/test', {
  param: 'value'
});
```

### 添加自定义业务错误处理
```javascript
const { post } = require('../../utils/request');

try {
  const result = await post('/api/test', {
    param: 'value'
  }, {
    // 自定义业务错误回调（不会覆盖默认的错误提示）
    onBusinessError: (responseData, errorMsg) => {
      console.log('业务错误详情:', responseData);
      console.log('错误消息:', errorMsg);
      
      // 可以根据具体错误码做不同处理
      if (responseData.code === 'VALIDATION_ERROR') {
        // 处理验证错误
        this.handleValidationError(responseData.data);
      } else if (responseData.code === 'PERMISSION_DENIED') {
        // 处理权限错误
        wx.redirectTo({ url: '/pages/login/login' });
      }
      
      // 可以记录错误日志
      this.logError('business_error', responseData);
    }
  });
} catch (error) {
  // 这里仍然会捕获到错误
  console.log('请求失败:', error);
}
```

### 添加自定义网络错误处理
```javascript
const { post } = require('../../utils/request');

try {
  const result = await post('/api/test', {
    param: 'value'
  }, {
    // 自定义网络错误回调
    onNetworkError: (err, errorMsg) => {
      console.log('网络错误详情:', err);
      console.log('错误消息:', errorMsg);
      
      // 可以根据错误类型做不同处理
      if (err.errMsg && err.errMsg.includes('timeout')) {
        // 超时处理
        this.handleTimeout();
      } else if (err.errMsg && err.errMsg.includes('fail')) {
        // 网络连接失败处理
        this.handleNetworkFail();
      }
      
      // 记录网络错误
      this.logError('network_error', err);
    }
  });
} catch (error) {
  console.log('请求失败:', error);
}
```

### 同时使用两种回调
```javascript
const { post } = require('../../utils/request');

try {
  const result = await post('/api/test', {
    param: 'value'
  }, {
    // 业务错误回调
    onBusinessError: (responseData, errorMsg) => {
      // 处理业务逻辑错误
      this.handleBusinessError(responseData);
    },
    
    // 网络错误回调
    onNetworkError: (err, errorMsg) => {
      // 处理网络错误
      this.handleNetworkError(err);
    }
  });
} catch (error) {
  console.log('请求失败:', error);
}
```

## 实际应用示例

### 表单提交场景
```javascript
async submitForm() {
  try {
    const result = await post('/api/submit-form', this.data.formData, {
      loadingTitle: '提交中...',
      onBusinessError: (responseData, errorMsg) => {
        // 处理表单验证错误
        if (responseData.code === 'VALIDATION_ERROR') {
          this.showValidationErrors(responseData.data.errors);
        }
      },
      onNetworkError: (err, errorMsg) => {
        // 网络错误时提供重试选项
        wx.showModal({
          title: '网络错误',
          content: '提交失败，是否重试？',
          success: (res) => {
            if (res.confirm) {
              this.submitForm(); // 重试
            }
          }
        });
      }
    });
    
    // 提交成功
    this.showSuccess('提交成功');
    wx.navigateBack();
    
  } catch (error) {
    // 这里会捕获所有错误（业务错误和网络错误）
    console.log('提交失败:', error);
  }
}
```

## 重要说明

1. **不会覆盖默认行为** - 自定义回调是在默认错误处理之后执行的
2. **错误仍会被抛出** - 即使有自定义回调，Promise 仍然会被 reject
3. **回调执行安全** - 如果回调函数执行出错，不会影响主流程
4. **可选配置** - 不配置回调时，保持原有行为不变

这样您就可以在保持现有错误提示功能的同时，添加自己的特殊处理逻辑了！
