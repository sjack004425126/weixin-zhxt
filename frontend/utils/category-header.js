/**
 * 解析 zs_category.extra_info（后端已转为 dict）为页面头部数据。
 *
 * 约定：键为字符串数字 "1","2","3"...，按数字升序排列。
 *  - 第 1 个 -> 顶部徽章 headerBadge
 *  - 最后 1 个 -> 副标题 headerSubtitle
 *  - 中间所有项 -> 标题行数组 headerTitles
 *
 * 边界情况：
 *  - 仅 1 项：作为标题
 *  - 仅 2 项：第 1 项为徽章，第 2 项为标题
 *  - 0 项 / 非对象：返回空结构
 *
 * @param {object} extraInfo
 * @returns {{ headerBadge: string, headerTitles: string[], headerSubtitle: string }}
 */
function parseCategoryHeader(extraInfo) {
  const empty = { headerBadge: '', headerTitles: [], headerSubtitle: '' };
  if (!extraInfo || typeof extraInfo !== 'object') return empty;

  const keys = Object.keys(extraInfo)
    .filter(k => extraInfo[k] !== undefined && extraInfo[k] !== null && extraInfo[k] !== '')
    .sort((a, b) => {
      const na = parseInt(a, 10);
      const nb = parseInt(b, 10);
      if (isNaN(na) || isNaN(nb)) return a.localeCompare(b);
      return na - nb;
    });

  const values = keys.map(k => String(extraInfo[k]));
  if (values.length === 0) return empty;
  if (values.length === 1) return { headerBadge: '', headerTitles: [values[0]], headerSubtitle: '' };
  if (values.length === 2) return { headerBadge: values[0], headerTitles: [values[1]], headerSubtitle: '' };
  return {
    headerBadge: values[0],
    headerTitles: values.slice(1, -1),
    headerSubtitle: values[values.length - 1]
  };
}

module.exports = { parseCategoryHeader };
