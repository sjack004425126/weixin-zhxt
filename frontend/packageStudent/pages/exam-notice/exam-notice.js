const app = getApp();
const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');


createPage({
  data: {
    studentInfo: {},
    exams: []
  },

  onLoad() {
    this.getExamNotice();
  },
  goHome(){
    wx.navigateTo({
      url: '/packageStudent/pages/my/my'
    });
  },
  async getExamNotice() {

    try{
      const resquest = await tokenGet('/student/get_exam_notice',{},{loadingTitle: '获取考试通知...'});

      const { student_info, exams } = resquest;
      this.setData({
        studentInfo: student_info,
        exams: exams
      });

    }catch(err){
      this.showError(err.message || "获取考试通知失败");
    }
  }
},{
  requireAuth: true,
  userType: 'open_student'
});
