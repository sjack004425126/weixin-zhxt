/**
 * 地区配置文件
 * 记录不同地区的书费价格
 */

// 地区书费配置
const AREA_BOOK_FEE_CONFIG = {
  '黔东南直属': 0, // 使用后台专业数据
  '丹寨': 900,
  '麻江': 900,
  '黄平': 900,
  '施秉': 900,
  '镇远': 900,
  '岑巩': 900,
  '三穗': 900,
  '天柱': 900,
  '锦屏': 900,
  '黎平': 900,
  '从江': 900,
  '榕江': 900,
  '雷山': 900,
  '台江': 900,
  '剑河': 900
};

// 三穗地区特殊专业配置
const SANSUI_SPECIAL_MAJORS = {
  26: 350, // 专业26的书费
  73: 350  // 专业73的书费
};

// 默认地区
const DEFAULT_AREA = '黔东南直属';

/**
 * 获取地区书费
 * @param {string} area - 地区名称
 * @param {number} majorId - 专业ID
 * @param {number} defaultBookFee - 默认书费（来自后台专业数据）
 * @returns {number} 书费金额
 */
function getAreaBookFee(area, majorId, defaultBookFee = 0) {
  // 如果没有传入地区，使用默认地区
  if (!area) {
    area = DEFAULT_AREA;
  }

  // 如果是黔东南直属，使用后台专业数据
  if (area === '黔东南直属') {
    return defaultBookFee;
  }

  // 三穗地区特殊专业处理
  if (area === '三穗' && SANSUI_SPECIAL_MAJORS[majorId]) {
    return SANSUI_SPECIAL_MAJORS[majorId];
  }

  // 其他地区按配置表匹配
  return AREA_BOOK_FEE_CONFIG[area] || AREA_BOOK_FEE_CONFIG[DEFAULT_AREA];
}

/**
 * 获取所有地区列表
 * @returns {Array} 地区列表
 */
function getAreaList() {
  return Object.keys(AREA_BOOK_FEE_CONFIG);
}

/**
 * 验证地区是否存在
 * @param {string} area - 地区名称
 * @returns {boolean} 是否存在
 */
function isValidArea(area) {
  return AREA_BOOK_FEE_CONFIG.hasOwnProperty(area);
}

/**
 * 获取地区显示信息
 * @param {string} area - 地区名称
 * @returns {Object} 地区信息
 */
function getAreaInfo(area) {
  if (!area || !isValidArea(area)) {
    area = DEFAULT_AREA;
  }

  return {
    name: area,
    isDefault: area === DEFAULT_AREA,
    bookFee: AREA_BOOK_FEE_CONFIG[area],
    isSpecial: area === '三穗' // 三穗有特殊专业
  };
}

module.exports = {
  AREA_BOOK_FEE_CONFIG,
  SANSUI_SPECIAL_MAJORS,
  DEFAULT_AREA,
  getAreaBookFee,
  getAreaList,
  isValidArea,
  getAreaInfo
};
