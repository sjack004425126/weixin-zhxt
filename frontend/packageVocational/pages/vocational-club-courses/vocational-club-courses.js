const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, get } = require('../../../utils/request');
const app = getApp();

// 选课/退选冷却时间：5 秒内不允许对同一课程再次操作（防抖）
const OPERATION_COOLDOWN_MS = 1000;
// 全局操作锁：同一时间只能有一个选课/退选请求在飞行中
let _operationInFlight = false;
// 每门课程的最后操作时间
const _lastOperationTime = {};
createPage({
  data: {
    courses: [],
    filteredCourses: [],
    selectedCourses: [],
    categories: [
      { id: 'all', name: '全部' }
    ],
    selectedCategory: 'all',
    searchKeyword: '',
    userInfo: null,
    allCourses: [],
    // 每门课程的冷却剩余秒数（前端禁用按钮）
    cooldownMap: {},
    // 是否显示返回顶部按钮
    showBackToTop: false,
    // 社团报名开关状态：true=关闭（前端阻止选/退操作），false/null=开启
    _clubSignupLocked: false,
    _clubSignupTip: ''
  },

  onLoad: function() {
    // 二次判断开关状态：关闭时不阻塞进入页面，仅在顶部展示内嵌 banner，
    // 学生仍可查看课程列表和自己已选课程，但无法进行选/退选操作
    this.checkClubSignupSwitch();

    const userInfo = app.getUserInfo();
    this.setData({
      userInfo: userInfo
    });
    this.fetchCourses();
  },

  /**
   * 检查社团报名功能开关。
   * - 关闭：设置 _clubSignupLocked=true，wxml 自动渲染内嵌 banner（不遮盖页面）
   * - 开启：清除锁状态，banner 自动隐藏
   * - 检查失败：默认放行（不影响使用）
   */
  async checkClubSignupSwitch() {
    try {
      const res = await get('/feature_switch/check/st_club_signup', {}, { showLoading: false });
      const data = (typeof res === 'object' && res !== null)
        ? res
        : { is_enabled: true, tip_message: '' };
      const isEnabled = data.is_enabled === true;
      this.setData({
        _clubSignupLocked: !isEnabled,
        _clubSignupTip: isEnabled ? '' : (data.tip_message || '社团报名功能已关闭')
      });
    } catch (e) {
      console.warn('[vocational-club-courses] 检查开关失败，默认放行:', e);
    }
  },

  // 监听页面滚动 - 控制返回顶部按钮显示
  onPageScroll: function(e) {
    const scrollTop = e.scrollTop;
    const shouldShow = scrollTop > 600;
    if (shouldShow !== this.data.showBackToTop) {
      this.setData({ showBackToTop: shouldShow });
    }
  },

  // 返回顶部
  onBackToTop: function() {
    wx.pageScrollTo({
      scrollTop: 0,
      duration: 300
    });
  },

  // 获取课程列表
  async fetchCourses() {
    try{
      const request = await tokenGet('/vocational_info/get_st_courses', {keyword:this.data.searchKeyword}, { loadingTitle: '获取社团课列表...' });
      // 获取已选课程ID列表
      const selectedCourseIds = request.selected_courses.map(course => course.course_id);
      
      // 处理课程数据，标记已选状态
      const courses = request.courses.map(course => ({
        ...course,
        category: course.category.trim(), // 去除多余空格
        selected: selectedCourseIds.includes(course.course_id)
      }));

      // 提取并更新分类列表
      const categories = [{ id: 'all', name: '全部' }];
      const categorySet = new Set();
      courses.forEach(course => {
        if (!categorySet.has(course.category)) {
          categorySet.add(course.category);
          categories.push({
            id: course.category,
            name: course.category
          });
        }
      });

      this.setData({ 
        courses,
        allCourses: courses,
        filteredCourses: courses,
        categories,
        selectedCourses: request.selected_courses
      });
    }catch(err){
      this.showError(err.errMsg || '获取课程列表失败');
    }


  },

  // 搜索和过滤
  filterCourses: function() {
    const { allCourses, selectedCategory, searchKeyword } = this.data;
    
    let filteredCourses = allCourses;

    // 分类过滤
    if (selectedCategory !== 'all') {
      filteredCourses = filteredCourses.filter(course => 
        course.category.trim() === selectedCategory
      );
    }

    // 关键词搜索
    if (searchKeyword) {
      const keyword = searchKeyword.toLowerCase();
      filteredCourses = filteredCourses.filter(course => 
        course.course_name.toLowerCase().includes(keyword) ||
        course.teacher_name.toLowerCase().includes(keyword) ||
        course.description.toLowerCase().includes(keyword)
      );
    }

    this.setData({
      filteredCourses
    });
  },

  // 搜索输入处理
  onSearchInput: function(e) {
    this.setData({
      searchKeyword: e.detail.value
    });
    this.filterCourses();
  },

  // 清空搜索关键词
  onClearSearch: function() {
    this.setData({
      searchKeyword: ''
    });
    this.filterCourses();
  },

  // 分类选择处理
  onCategorySelect: function(e) {
    const categoryId = e.currentTarget.dataset.id;
    this.setData({
      selectedCategory: categoryId
    });
    this.filterCourses();
  },

  // 启动某门课程的冷却倒计时（前端禁用按钮）
  startCooldown(courseId) {
    _lastOperationTime[courseId] = Date.now();
    const cooldownMap = { ...this.data.cooldownMap, [courseId]: 5 };
    this.setData({ cooldownMap });
    const tick = () => {
      const elapsed = Date.now() - (_lastOperationTime[courseId] || 0);
      const remaining = Math.max(0, Math.ceil((OPERATION_COOLDOWN_MS - elapsed) / 1000));
      const map = { ...this.data.cooldownMap };
      if (remaining > 0) {
        map[courseId] = remaining;
        this.setData({ cooldownMap: map });
        setTimeout(tick, 1000);
      } else {
        delete map[courseId];
        delete _lastOperationTime[courseId];
        this.setData({ cooldownMap: map });
      }
    };
    setTimeout(tick, 1000);
  },

  // 选择课程
  async onCourseSelect(e) {
    // 功能开关关闭：轻提示并阻止选课（页面顶部 banner 已展示原因）
    if (this.data._clubSignupLocked) {
      wx.showToast({
        title: this.data._clubSignupTip || '社团报名功能已关闭',
        icon: 'none',
        duration: 2500
      });
      return;
    }

    // 全局锁：同一时刻只允许一个选/退请求
    if (_operationInFlight) {
      this.showError('操作进行中，请稍候');
      return;
    }
    const course = e.currentTarget.dataset.course;

    // 前端冷却检查
    if (_lastOperationTime[course.course_id] &&
        Date.now() - _lastOperationTime[course.course_id] < OPERATION_COOLDOWN_MS) {
      const wait = Math.ceil((OPERATION_COOLDOWN_MS - (Date.now() - _lastOperationTime[course.course_id])) / 1000);
      this.showError(`请 ${wait} 秒后再试`);
      return;
    }

    // 检查是否已选
    if (course.selected) {
      this.showError('该课程已选');
      return;
    }

    // 检查剩余名额
    if (course.available_slots <= 0) {
      this.showError('该课程已无剩余名额');
      return;
    }

    // 检查已选课程数量
    if (this.data.selectedCourses.length >= 1) {
      this.showError('最多只能选择一门社团课');
      return;
    }

    // 发起选课请求
    _operationInFlight = true;
    this.startCooldown(course.course_id);
    try{
      await tokenGet('/vocational_info/select_st_course', {course_id: course.course_id}, { loadingTitle: '选课中...' });

      // 更新已选课程列表
      const selectedCourse = {
      ...course,
      course_id: course.course_id,
      course_name: course.course_name,
      classroom: course.classroom,
      teacher_name: course.teacher_name,
      description: course.description
    };
    const selectedCourses = [...this.data.selectedCourses, selectedCourse];

    // 更新所有相关课程列表中的选中状态和人数
    const updateCourseList = (list) => list.map(c => {
      if (c.course_id === course.course_id) {
        return {
          ...c,
          selected: true,
          current_students: c.current_students + 1,
          available_slots: c.available_slots - 1
        };
      }
      return c;
    });

    this.setData({
      selectedCourses,
      allCourses: updateCourseList(this.data.allCourses),
      filteredCourses: updateCourseList(this.data.filteredCourses)
    });
    }catch(err){
      this.showError(err.errMsg || '选课失败');
    } finally {
      _operationInFlight = false;
    }
  },

  // 退选课程
  onCourseCancel: function(e) {
    // 功能开关关闭：轻提示并阻止退选（页面顶部 banner 已展示原因）
    if (this.data._clubSignupLocked) {
      wx.showToast({
        title: this.data._clubSignupTip || '社团报名功能已关闭',
        icon: 'none',
        duration: 2500
      });
      return;
    }

    if (_operationInFlight) {
      this.showError('操作进行中，请稍候');
      return;
    }
    const course = e.currentTarget.dataset.course;

    // 前端冷却检查
    if (_lastOperationTime[course.course_id] &&
        Date.now() - _lastOperationTime[course.course_id] < OPERATION_COOLDOWN_MS) {
      const wait = Math.ceil((OPERATION_COOLDOWN_MS - (Date.now() - _lastOperationTime[course.course_id])) / 1000);
      this.showError(`请 ${wait} 秒后再试`);
      return;
    }

    wx.showModal({
      title: '确认退选',
      content: '确定要退选该课程吗？',
      success: async (res) => {
        if (res.confirm) {
          if (_operationInFlight) {
            this.showError('操作进行中，请稍候');
            return;
          }
          _operationInFlight = true;
          this.startCooldown(course.course_id);
          try{
            await tokenGet('/vocational_info/cancel_st_course', {course_id: course.course_id}, { loadingTitle: '退选中...' });
            // 更新已选课程列表
            const selectedCourses = this.data.selectedCourses.filter(
              c => c.course_id !== course.course_id
            );

            // 更新所有相关课程列表中的选中状态
            const updateCourseList = (list) => list.map(c => {
              if (c.course_id === course.course_id) {
                return {
                  ...c,
                  selected: false,
                  current_students: c.current_students - 1,
                  available_slots: c.available_slots + 1
                };
              }
              return c;
            });

            this.setData({
              selectedCourses,
              allCourses: updateCourseList(this.data.allCourses),
              filteredCourses: updateCourseList(this.data.filteredCourses)
            });
          }catch(err){
            this.showError(err.errMsg || '退选失败');
          } finally {
            _operationInFlight = false;
          }

        }
      }
    });
  },

  // 清除筛选
  onClearFilter: function() {
    this.setData({
      searchKeyword: '',
      selectedCategory: 'all'
    });
    this.filterCourses();
  }
},{
  requireAuth: true,
  userType: 'vocational_student'
});