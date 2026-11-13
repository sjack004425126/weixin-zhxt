// utils/base64.js - 微信小程序兼容的base64编解码工具

/**
 * Base64编码表
 */
const BASE64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

/**
 * Base64编码
 * @param {string} str - 要编码的字符串
 * @returns {string} - base64编码后的字符串
 */
function base64Encode(str) {
  let result = '';
  let i = 0;
  
  // 将字符串转换为UTF-8字节数组
  const utf8Bytes = encodeURIComponent(str).replace(/%([0-9A-F]{2})/g, (match, p1) => {
    return String.fromCharCode(parseInt(p1, 16));
  });
  
  while (i < utf8Bytes.length) {
    const a = utf8Bytes.charCodeAt(i++);
    const b = i < utf8Bytes.length ? utf8Bytes.charCodeAt(i++) : 0;
    const c = i < utf8Bytes.length ? utf8Bytes.charCodeAt(i++) : 0;
    
    const bitmap = (a << 16) | (b << 8) | c;
    
    result += BASE64_CHARS.charAt((bitmap >> 18) & 63);
    result += BASE64_CHARS.charAt((bitmap >> 12) & 63);
    result += (i - 2) < utf8Bytes.length ? BASE64_CHARS.charAt((bitmap >> 6) & 63) : '=';
    result += (i - 1) < utf8Bytes.length ? BASE64_CHARS.charAt(bitmap & 63) : '=';
  }
  
  return result;
}

/**
 * Base64解码
 * @param {string} base64Str - base64编码的字符串
 * @returns {string} - 解码后的字符串
 */
function base64Decode(base64Str) {
  try {
    // 移除空白字符
    base64Str = base64Str.replace(/\s/g, '');
    
    // 检查base64格式
    if (!/^[A-Za-z0-9+/]*={0,2}$/.test(base64Str)) {
      throw new Error('Invalid base64 string');
    }
    
    let result = '';
    let i = 0;
    
    while (i < base64Str.length) {
      const encoded1 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      const encoded2 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      const encoded3 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      const encoded4 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      
      const bitmap = (encoded1 << 18) | (encoded2 << 12) | (encoded3 << 6) | encoded4;
      
      result += String.fromCharCode((bitmap >> 16) & 255);
      if (encoded3 !== 64) {
        result += String.fromCharCode((bitmap >> 8) & 255);
      }
      if (encoded4 !== 64) {
        result += String.fromCharCode(bitmap & 255);
      }
    }
    
    // 将字节数组转换回UTF-8字符串
    return decodeURIComponent(result.split('').map(c => {
      return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));
    
  } catch (error) {
    console.error('Base64解码失败:', error);
    return '';
  }
}

/**
 * 微信小程序兼容的atob函数
 * @param {string} base64Str - base64编码的字符串
 * @returns {string} - 解码后的原始字节字符串
 */
function atob(base64Str) {
  try {
    // 移除空白字符
    base64Str = base64Str.replace(/\s/g, '');
    
    // 检查base64格式
    if (!/^[A-Za-z0-9+/]*={0,2}$/.test(base64Str)) {
      throw new Error('Invalid base64 string');
    }
    
    let result = '';
    let i = 0;
    
    while (i < base64Str.length) {
      const encoded1 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      const encoded2 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      const encoded3 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      const encoded4 = BASE64_CHARS.indexOf(base64Str.charAt(i++));
      
      const bitmap = (encoded1 << 18) | (encoded2 << 12) | (encoded3 << 6) | encoded4;
      
      result += String.fromCharCode((bitmap >> 16) & 255);
      if (encoded3 !== 64) {
        result += String.fromCharCode((bitmap >> 8) & 255);
      }
      if (encoded4 !== 64) {
        result += String.fromCharCode(bitmap & 255);
      }
    }
    
    return result;
    
  } catch (error) {
    console.error('atob解码失败:', error);
    return '';
  }
}

/**
 * 微信小程序兼容的btoa函数
 * @param {string} str - 要编码的字符串
 * @returns {string} - base64编码后的字符串
 */
function btoa(str) {
  let result = '';
  let i = 0;
  
  while (i < str.length) {
    const a = str.charCodeAt(i++);
    const b = i < str.length ? str.charCodeAt(i++) : 0;
    const c = i < str.length ? str.charCodeAt(i++) : 0;
    
    const bitmap = (a << 16) | (b << 8) | c;
    
    result += BASE64_CHARS.charAt((bitmap >> 18) & 63);
    result += BASE64_CHARS.charAt((bitmap >> 12) & 63);
    result += (i - 2) < str.length ? BASE64_CHARS.charAt((bitmap >> 6) & 63) : '=';
    result += (i - 1) < str.length ? BASE64_CHARS.charAt(bitmap & 63) : '=';
  }
  
  return result;
}

/**
 * 解码URL安全的base64字符串（用于微信小程序场景参数）
 * @param {string} urlSafeBase64 - URL安全的base64字符串
 * @returns {string} - 解码后的UTF-8字符串
 */
function decodeUrlSafeBase64(urlSafeBase64) {
  try {
    // 1. 将URL安全字符替换回标准base64字符
    let base64Str = urlSafeBase64.replace(/-/g, '+').replace(/_/g, '/');
    
    // 2. 补齐padding
    while (base64Str.length % 4 !== 0) {
      base64Str += '=';
    }
    
    // 3. 使用自定义的atob函数解码
    const decoded = atob(base64Str);
    
    // 4. 转换为UTF-8字符串
    const utf8String = decodeURIComponent(Array.prototype.map.call(decoded, c =>
      '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
    ).join(''));
    
    return utf8String;
    
  } catch (error) {
    console.error('URL安全base64解码失败:', error);
    return '';
  }
}

// CommonJS导出
module.exports = {
  base64Encode,
  base64Decode,
  atob,
  btoa,
  decodeUrlSafeBase64
};
