const { createPage } = require('../../../utils/page-mixin');

createPage({
  data: {
    items: [1, 2, 3, 4, 5, 6],
    selectedMap: {},
    selectedCount: 0,
    debugInfo: ''
  },

  toggle(e) {
    const id = '' + e.currentTarget.dataset.id;
    const map = Object.assign({}, this.data.selectedMap);
    if (map[id]) {
      delete map[id];
    } else {
      map[id] = true;
    }
    const count = Object.keys(map).length;
    const debugInfo = 'tap id=' + id + ' | keys=' + JSON.stringify(Object.keys(map));
    console.log(debugInfo);
    this.setData({ selectedMap: map, selectedCount: count, debugInfo: debugInfo });
  }
});
