const { createPage } = require('../../../utils/page-mixin');

createPage({
  data: {
    searchKeyword: '',
    selectedCategory: '全部',
    categories: ['全部', '学习相关', '系统操作', '考试相关', '其他'],
    qaList: [
      {
        id: 1,
        question: '必须得在课程剩余作答时间内完成吗？',
        category: '考试相关',
        type: 'simple',
        answer: '是的，一般终考试卷和行考作业都有截止时间的说明，请务必在规定时间内完成。',
        expanded: false,
        helpful: 15
      },
      {
        id: 2,
        question: '如何登陆学生综合平台查成绩，交补考费，打印准考证？',
        category: '系统操作',
        type: 'detailed',
        intro: '如果你需要查询自己学习相关的信息，需要登陆黔东南开放大学的学生综合平台（教务系统）。登陆流程如下：',
        steps: [
          {
            title: '安装atrust软件',
            description: '手机端到华为应用市场去搜索下载，电脑端则访问网站https://vpn.qdndd.com.cn这个网址，首页右上角有个"下载客户端"的链接，下载电脑端安装即可。'
          },
          {
            title: '登陆atrust这个vpn软件',
            description: '打开atrust，首次打开需要输入vpn的网址，填写：https://vpn.qdndd.com.cn即可，然后点击登陆，然后弹出认证界面，输入用户名和密码。',
            highlight: ['用户名：学号', '密码：Ouchn@出生年月日']
          },
          {
            title: '打开学生综合平台',
            description: '成功登陆atrust这个vpn软件后，软件首页有个图标"学生综合平台"，点击以后即可自动登陆了。'
          },
          {
            title: '查看相关信息',
            description: '进入学生综合平台以后，即可查看自己的成绩，教学计划，交补考费，打印准考证。'
          }
        ],
        expanded: false,
        helpful: 32
      },
      {
        id: 3,
        question: '如何修改登录密码？',
        category: '系统操作',
        type: 'simple',
        answer: '登录学生综合平台后，点击右上角个人信息，选择"修改密码"，输入原密码和新密码即可完成修改。',
        expanded: false,
        helpful: 8
      },
      {
        id: 4,
        question: '忘记学号怎么办？',
        category: '学习相关',
        type: 'simple',
        answer: '请联系班主任或教务老师，提供身份证号码和姓名，即可查询到您的学号信息。',
        expanded: false,
        helpful: 12
      }
    ],
    filteredQaList: []
  },

  onLoad() {
    // 初始化过滤列表
    this.filterQaList();

    // 设置页面标题
    wx.setNavigationBarTitle({
      title: '常见问题'
    });
  },

  // 搜索输入
  onSearchInput(e) {
    this.setData({
      searchKeyword: e.detail.value
    });
    this.filterQaList();
  },

  // 清除搜索
  clearSearch() {
    this.setData({
      searchKeyword: ''
    });
    this.filterQaList();
  },

  // 选择分类
  selectCategory(e) {
    const category = e.currentTarget.dataset.category;
    this.setData({
      selectedCategory: category
    });
    this.filterQaList();
    wx.vibrateShort(); // 触觉反馈
  },

  // 过滤问答列表
  filterQaList() {
    let filtered = this.data.qaList;

    // 按分类过滤
    if (this.data.selectedCategory !== '全部') {
      filtered = filtered.filter(item => item.category === this.data.selectedCategory);
    }

    // 按关键词过滤
    if (this.data.searchKeyword) {
      const keyword = this.data.searchKeyword.toLowerCase();
      filtered = filtered.filter(item =>
        item.question.toLowerCase().includes(keyword) ||
        (item.answer && item.answer.toLowerCase().includes(keyword))
      );
    }

    this.setData({
      filteredQaList: filtered
    });
  },

  // 切换展开/收起
  toggleExpand(e) {
    const index = e.currentTarget.dataset.index;
    const item = this.data.filteredQaList[index];
    const qaIndex = this.data.qaList.findIndex(qa => qa.id === item.id);

    this.setData({
      [`qaList[${qaIndex}].expanded`]: !item.expanded
    });

    // 更新过滤列表
    this.filterQaList();
    wx.vibrateShort(); // 触觉反馈
  },

  // 标记有帮助
  markHelpful(e) {
    const index = e.currentTarget.dataset.index;
    const item = this.data.filteredQaList[index];
    const qaIndex = this.data.qaList.findIndex(qa => qa.id === item.id);

    this.setData({
      [`qaList[${qaIndex}].helpful`]: (item.helpful || 0) + 1
    });

    this.filterQaList();

    wx.showToast({
      title: '感谢您的反馈！',
      icon: 'success'
    });
    wx.vibrateShort();
  },

  // 复制答案
  copyAnswer(e) {
    const index = e.currentTarget.dataset.index;
    const item = this.data.filteredQaList[index];

    let copyText = `问题：${item.question}\n\n答案：`;

    if (item.type === 'simple') {
      copyText += item.answer;
    } else if (item.type === 'detailed') {
      copyText += item.intro + '\n\n';
      item.steps.forEach((step, stepIndex) => {
        copyText += `${stepIndex + 1}. ${step.title}\n${step.description}\n`;
        if (step.highlight) {
          step.highlight.forEach(highlight => {
            copyText += `   ${highlight}\n`;
          });
        }
        copyText += '\n';
      });
    }

    wx.setClipboardData({
      data: copyText,
      success: () => {
        wx.showToast({
          title: '已复制到剪贴板',
          icon: 'success'
        });
      }
    });
    wx.vibrateShort();
  },

  // 联系客服
  contactService() {
    wx.showModal({
      title: '联系客服',
      content: '请拨打办公室电话：0855-8501978\n或添加微信客服获取帮助',
      confirmText: '拨打电话',
      cancelText: '取消',
      success: (res) => {
        if (res.confirm) {
          wx.makePhoneCall({
            phoneNumber: '0855-8501978'
          });
        }
      }
    });
  },

  // 提交问题
  submitQuestion() {
    wx.navigateTo({
      url: '/pages/feedback/feedback'
    });
  },

  // 分享功能
  onShareAppMessage() {
    return {
      title: '黔东南开放大学常见问题',
      path: '/pages/qa/qa'
    };
  },

  onShareTimeline() {
    return {
      title: '黔东南开放大学常见问题'
    };
  }
})