const { createPage } = require('../../../utils/page-mixin');

createPage({
  goToOpenEnroll() {
    wx.navigateTo({ url: '/pages/enroll/enroll' });
  },
  goToVocationalEnroll() {
    wx.navigateTo({ url: '/packageVocational/pages/vocational-enroll/vocational-enroll' });
  },
  goToAdultExam() {
    wx.navigateTo({ url: '/packageEnroll/pages/adult-enroll/adult-enroll' });
  }
}) 