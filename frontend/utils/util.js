const formatTime = date => {
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()
  const hour = date.getHours()
  const minute = date.getMinutes()
  const second = date.getSeconds()

  return `${[year, month, day].map(formatNumber).join('/')} ${[hour, minute, second].map(formatNumber).join(':')}`
}

const formatNumber = n => {
  n = n.toString()
  return n[1] ? n : `0${n}`
}

// ============================================================
// 身份证号码校验
// ============================================================

// 18 位身份证前 17 位的加权因子
const ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
// 余数 -> 校验码
const ID_CHECK_CODES = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']

/**
 * 校验 18 位身份证的出生日期段是否合法
 * @param {string} dateStr 形如 "19900101"
 * @returns {boolean}
 */
function isValidIdCardDate(dateStr) {
  const year = Number(dateStr.slice(0, 4))
  const month = Number(dateStr.slice(4, 6))
  const day = Number(dateStr.slice(6, 8))

  if (!year || !month || !day) return false
  if (month < 1 || month > 12) return false
  if (day < 1 || day > 31) return false

  const d = new Date(year, month - 1, day)
  return d.getFullYear() === year && d.getMonth() === month - 1 && d.getDate() === day
}

/**
 * 校验身份证号码格式
 *
 * 支持 15 位（旧身份证）和 18 位（GB 11643-1999）：
 * - 18 位：前 17 位为数字，第 18 位为数字或 X（不区分大小写），
 *          并校验出生日期与 ISO 7064:1983 MOD 11-2 校验码
 * - 15 位：15 位纯数字，并校验出生日期
 *
 * @param {string} idCard
 * @returns {boolean} 格式是否合法
 */
function isValidIdCard(idCard) {
  if (idCard === undefined || idCard === null) return false
  const v = String(idCard).trim()
  if (!v) return false

  // 18 位
  if (/^\d{17}[\dXx]$/.test(v)) {
    const body = v.slice(0, 17)
    if (!isValidIdCardDate(v.slice(6, 14))) return false

    // 校验码：加权求和后对 11 取模
    let sum = 0
    for (let i = 0; i < 17; i++) {
      sum += Number(body[i]) * ID_WEIGHTS[i]
    }
    const expect = ID_CHECK_CODES[sum % 11]
    return v[17].toUpperCase() === expect
  }

  // 15 位
  if (/^\d{15}$/.test(v)) {
    // 15 位出生日期为 "YYMMDD"，按 19xx 解析
    return isValidIdCardDate('19' + v.slice(6, 12))
  }

  return false
}

/**
 * 校验手机号码（中国大陆）
 * @param {string} phone
 * @returns {boolean}
 */
function isValidPhone(phone) {
  if (phone === undefined || phone === null) return false
  return /^1[3-9]\d{9}$/.test(String(phone).trim())
}

module.exports = {
  formatTime,
  isValidIdCard,
  isValidPhone
}
