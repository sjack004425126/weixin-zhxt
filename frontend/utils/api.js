// API 基础配置
// const BASE_URL = 'https://m.qdndd.com.cn';
const BASE_URL = 'http://127.0.0.1:443';
// API 路径配置
const API = {
  // 首页页面接口
  HOME: {
    BANNER: '/banner/list',
    NOTICE: '/notice/list'
  },
  
  // 个人中心页面接口
  MY: {
    UPDATE_AVATAR: '/student/updateAvatar'
  },

  VOCATIONAL_MY: {
    UPDATE_AVATAR: '/vocational/updateAvatar'
  },

  APP: {
    GET_USER_OPENID: '/student/getUserOpenid'
  },

  // 新生缴费页面接口
  NEW_STUDENT_PAYMENT: {
    MAJORS: '/freshman/majors/all',
    PRE_PAY: '/freshman/prePay',
    UPDATE_PAY: '/freshman/updatePayStatus'
  },

  PAYMENT_BUKAO: {
    LIST: '/student/scores/bkDetail',
    PRE_BK_PAY: '/student/courses/preBkPay',
    BK_PAY: '/student/courses/bkPay',
    UPDATE_PRE_BK_ORDER: '/student/updateBkPayStatus',
    PAY_BK_BY_ORDER_NO: '/student/payBkByOrderNo',
  },
  
  // 缴费记录页面接口
  PAYMENT_RECORDS: {
    LIST: '/student/getOrderList',
    PAY_BY_ORDER_NO: '/student/payXfByOrderNo',
    UPDATE_ORDER: '/student/updateOrderStatus'
  },
  MY_COURSES: {
    LIST: '/course/get_course_list_all',
    MANAGEMENT_LIST: '/course_management/get_course_list_all',
    SEMESTER_LIST: '/course/get_course_list'
  },



  // 毕业生登记表页面接口
  GRADUATE_FORM: {
    // 获取毕业生登记表信息
    GET_INFO: '/student/graduate_registration',
    // 提交毕业生登记表
    SUBMIT: '/student/graduate_registration'
  },

  // 成绩页面接口
  SCORE: {
    // 获取成绩列表
    GET_LIST: '/student/scores',
    REVIEW: '/student/score/review'
  },

  // 学生相关接口
  STUDENT: {
    // 获取形势与政策成绩
    POLITICS_SCORES: '/student/politics/scores'
  },

  // 课程页面接口
  COURSES: {
    // 获取课程列表
    GET_LIST: '/student/courses'
  },

  // 学费页面接口
  TUITION: {
    // 获取学费信息
    GET_INFO: '/student/tuition',
    // 计算学费
    CALCULATE: '/student/tuition/calculate',
    // 获取预支付信息
    PRE_PAY: '/student/getPrePayInfo',
    // 更新订单状态
    UPDATE_ORDER: '/student/updateOrderStatus'
  },

  // 毕业证书状态页面接口
  DIPLOMA: {
    // 获取毕业证书状态
    GET_STATUS: '/student/get_diploma_status'
  },

  // 专业介绍页面接口
  MAJOR: {
    // 获取所有专业列表
    GET_ALL: '/freshman/majors/all'
  },

  // 考试通知页面接口
  EXAM: {
    // 获取考试通知
    GET_NOTICE: '/student/exam_notice'
  },

  LOGIN: {
    LOGIN: '/login/login',
    VERIFY: '/login/verifyUser',
    // openid 快捷登录（微信一键登录）
    OPENID_LOGIN: '/login/quickLogin',
    // 微信手机号快捷登录
    PHONE_QUICK_LOGIN: '/login/phone_quick_login'
  },


  VOCATIONAL_LOGIN: {
    LOGIN: '/vocational_login/login',
    VERIFY: '/vocational_login/verifyUser',
    // openid 快捷登录（微信一键登录）
    OPENID_LOGIN: '/vocational_login/quickLogin',
    // 微信手机号快捷登录
    PHONE_QUICK_LOGIN: '/vocational_login/phone_quick_login'
  },

  // 教师端登录
  TEACHER_LOGIN: {
    // 开放教师：openid 一键登录
    OPEN_TEACHER_OPENID_LOGIN: '/open_teacher/quick_login_openid',
    // 开放教师：手机号快捷登录
    OPEN_TEACHER_PHONE_QUICK_LOGIN: '/open_teacher/quick_login',
    // 中职教师：openid 一键登录
    VOCATIONAL_TEACHER_OPENID_LOGIN: '/vocational_teacher/quick_login_openid',
    // 中职教师：手机号快捷登录
    VOCATIONAL_TEACHER_PHONE_QUICK_LOGIN: '/vocational_teacher/quick_login'
  },

  VOCATIONAL_TUITION: {
    // 获取学费信息
    GET_INFO: '/vocational/paymentInfo',
    // 获取支付参数
    PRE_PAYMENT: '/vocational/prePayment',
    // 更新订单状态
    UPDATE_ORDER_STATUS: '/vocational/updateOrderStatus'
  },

  VOCATIONAL_CLUB_COURSES: {
    LIST: '/vocational/st_courses',
    SELECT: '/vocational/st_select_course',
    CANCEL: '/vocational/st_cancel_course'
  },

  DEGREE_ENGLISH: {
    GET_DEGREE_ENGLISH_INFO: '/degree/degree_english_info',
    REGISTER: '/degree/create_degree_english_order',
    PRE_PAY: '/degree/prepay_degree_english',
    UPDATE_DEGREE_ENGLISH_ORDER: '/degree/update_degree_english_order'
  },

  REFUND:{
    SEND_VERIFY_CODE:'/login/xwyy_get_phone_code',
    CHECK_PHONE_CODE_GENORDER:'/student/wxxs_checkPhoneCode_BindOpenid_genOrder',
    UPDATE_TK_PAYINFO_COMPLETE:'/student/update_wxxs_tk_payinfo_complete'
  },



  VOCATIONAL_ZZBM: {
    CREATE_ZZBM: '/zzbm/create_zzbm',
    GET_ZZBM_INFO: '/zzbm/get_new_zzbm_info',
    GENERATE_QRCODE: '/zzbm/generate_qrcode'
  },

  EXAM_LIST: {
    GET_EXAM_LIST: '/exame/subjectsList',
    // 新接入：exame 考试系统（中职学生）
    GET_EXAME_EXAMS: '/exame/exams'
  },


  EXAM_INFO: {
    GET_SJ_LIST: '/exame/get_sj_list',
    // 新接入：exame 考试详情
    GET_EXAME_DETAIL: (id) => `/exame/exams/${id}`
  },

  EXAME_PAPER: {
    GET_EXAM_PAPER: '/exame/get_exame_paper',
    SUBMIT_EXAM: '/exame/submit_exam',
    // 新接入：exame 开始考试 / 提交
    START_EXAME: '/exame/exams/start',
    SUBMIT_EXAME: '/exame/exams/submit'
  },

  EXAME_SCORE: {
    LIST: '/exame/exams/records',
    DETAIL: (id) => `/exame/exams/records/${id}`,
    PAPER: (id) => `/exame/exams/records/${id}/paper`
  }




};

// 完整 URL 生成器
const getUrl = (path) => `${BASE_URL}${path}`;

// 导出 API 配置
module.exports = {
  BASE_URL,
  API,
  getUrl
};