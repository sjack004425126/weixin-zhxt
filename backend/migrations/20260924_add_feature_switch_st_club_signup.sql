-- ============================================================
-- 新增社团报名功能开关
-- 说明：控制中职学生社团课报名/退选功能开关
--       code = 'st_club_signup'
--       关闭后学生访问 vocational-club-courses 页面会弹窗提示；
--       后端 select_st_course / cancel_st_course 接口也会校验，
--       关闭时直接返回 success=false，避免绕过前端。
-- 适用于 SQL Server（lw_feature_switch 表）
-- ============================================================

IF NOT EXISTS (SELECT 1 FROM lw_feature_switch WHERE code = 'st_club_signup')
BEGIN
    INSERT INTO lw_feature_switch
        (code, name, is_enabled, sort_order, remark, tip_message, created_at, updated_at)
    VALUES
        ('st_club_signup', '学生社团课报名', 1, 20,
         '中职学生社团课报名与退选功能总开关。关闭后学生无法报名或退选社团课',
         '社团报名功能已关闭，请联系管理员开启后再试',
         GETDATE(), GETDATE());
END
ELSE
BEGIN
    UPDATE lw_feature_switch
    SET name        = '学生社团课报名',
        sort_order  = 20,
        remark      = '中职学生社团课报名与退选功能总开关。关闭后学生无法报名或退选社团课',
        tip_message = '社团报名功能已关闭，请联系管理员开启后再试',
        updated_at  = GETDATE()
    WHERE code = 'st_club_signup';
END
GO
