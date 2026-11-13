var pageMixin = require('../../../utils/page-mixin');
var request = require('../../../utils/request');
var createPage = pageMixin.createPage;
var get = request.get;
var post = request.post;

createPage({
  data: {
    majorData: [],
    pickerValue: [0, 0, 0],
    typeList: [],
    levelList: [],
    majorList: [],
    selectedTypeName: '',
    selectedLevelName: '',
    selectedMajor: null,
    editTuition: '',
    editBooks: '',
    saving: false
  },

  onLoad: function() {
    // 直接加载数据，认证由 admin-nav 页面统一处理
    this.loadMajorData();
  },

  goBack: function() {
    wx.navigateBack();
  },

  loadMajorData: function() {
    var that = this;
    get('/freshman_tuition/get_majors_all', {}, { loadingTitle: '加载专业数据...' }).then(function(result) {
      var majorData = result;
      
      if (!majorData || majorData.length === 0) {
        that.showError('暂无专业数据');
        return;
      }
      
      var firstType = majorData[0];
      var firstLevel = firstType.levels[0];
      
      that.setData({
        majorData: majorData,
        typeList: majorData.map(function(item) { return item.name; }),
        levelList: firstType.levels.map(function(level) { return level.name; }),
        majorList: firstLevel.majors.map(function(major) { return major.name; }),
        pickerValue: [0, 0, 0]
      });
      
      that.updateSelectedMajor(0, 0, 0);
    }).catch(function() {
      that.showError('加载专业数据失败，请重试');
    });
  },

  onPickerViewChange: function(e) {
    var val = e.detail.value;
    var typeIdx = val[0];
    var levelIdx = val[1];
    var majorIdx = val[2];
    var majorData = this.data.majorData;
    var pickerValue = this.data.pickerValue;
    
    if (typeIdx !== pickerValue[0]) {
      var newType = majorData[typeIdx];
      
      // 如果该类型下没有层次数据，清空二级和三级
      if (!newType.levels || newType.levels.length === 0) {
        this.setData({
          pickerValue: [typeIdx, 0, 0],
          levelList: [],
          majorList: [],
          selectedTypeName: newType.name,
          selectedLevelName: '',
          selectedMajor: null,
          editTuition: '0',
          editBooks: '0'
        });
        return;
      }
      
      var newLevelList = newType.levels.map(function(l) { return l.name; });
      var newMajorList = newType.levels[0].majors.map(function(m) { return m.name; });
      
      this.setData({
        pickerValue: [typeIdx, 0, 0],
        levelList: newLevelList,
        majorList: newMajorList
      });
      this.updateSelectedMajor(typeIdx, 0, 0);
    } else if (levelIdx !== pickerValue[1]) {
      var currentType = majorData[typeIdx];
      var newLevel = currentType.levels[levelIdx];
      var newMajorList2 = newLevel.majors.map(function(m) { return m.name; });
      
      this.setData({
        pickerValue: [typeIdx, levelIdx, 0],
        majorList: newMajorList2
      });
      this.updateSelectedMajor(typeIdx, levelIdx, 0);
    } else {
      this.setData({ pickerValue: val });
      this.updateSelectedMajor(typeIdx, levelIdx, majorIdx);
    }
  },

  updateSelectedMajor: function(typeIdx, levelIdx, majorIdx) {
    var majorData = this.data.majorData;
    
    if (!majorData || !majorData[typeIdx]) return;
    
    var currentType = majorData[typeIdx];
    var currentLevel = currentType.levels[levelIdx];
    if (!currentLevel) return;
    
    var currentMajor = currentLevel.majors[majorIdx];
    
    if (currentMajor) {
      this.setData({
        selectedTypeName: currentType.name,
        selectedLevelName: currentLevel.name,
        selectedMajor: currentMajor,
        editTuition: String(currentMajor.tuition || 0),
        editBooks: String(currentMajor.books || 0)
      });
    }
  },

  onTuitionInput: function(e) {
    this.setData({ editTuition: e.detail.value });
  },

  onBooksInput: function(e) {
    this.setData({ editBooks: e.detail.value });
  },

  saveFees: function() {
    var that = this;
    var selectedMajor = this.data.selectedMajor;
    var editTuition = this.data.editTuition;
    var editBooks = this.data.editBooks;
    
    if (!selectedMajor) {
      this.showError('请先选择专业');
      return;
    }

    var tuition = parseInt(editTuition) || 0;
    var books = parseInt(editBooks) || 0;

    if (tuition < 0 || books < 0) {
      this.showError('费用不能为负数');
      return;
    }

    this.setData({ saving: true });

    post('/freshman_tuition/update_major_fees', {
      major_id: selectedMajor.id,
      tuition: tuition,
      books: books
    }, { loadingTitle: '保存中...' }).then(function() {
      that.showSuccess('保存成功');
      
      var majorData = that.data.majorData;
      var pickerValue = that.data.pickerValue;
      var typeIdx = pickerValue[0];
      var levelIdx = pickerValue[1];
      var majorIdx = pickerValue[2];
      
      majorData[typeIdx].levels[levelIdx].majors[majorIdx].tuition = tuition;
      majorData[typeIdx].levels[levelIdx].majors[majorIdx].books = books;
      
      that.setData({ 
        majorData: majorData,
        selectedMajor: {
          id: selectedMajor.id,
          name: selectedMajor.name,
          tuition: tuition,
          books: books
        },
        saving: false 
      });
    }).catch(function() {
      that.setData({ saving: false });
      that.showError('保存失败，请重试');
    });
  },

});
