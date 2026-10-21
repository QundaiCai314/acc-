import { state } from './state.js';
import { esc } from './ui.js';

export function passwordForm() {
  return '<h2>账号管理</h2><p>' + esc(state.identity.user_id) + ' · ' + esc(state.identity.workspace) + '</p>' +
    '<form id="change-password-form"><label>当前密码<input name="current_password" type="password" required maxlength="256" autocomplete="current-password"></label>' +
    '<label>新密码<input name="password" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label>' +
    '<label>确认新密码<input name="confirm_password" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label>' +
    '<p class="muted">修改后所有密码登录会话失效，请重新登录。新密码至少 12 个字符。</p>' +
    '<button class="button primary">修改密码</button></form>' +
    (state.identity.role === 'admin' ? '<button class="button" data-action="manage-members">成员与注册审批</button>' : '');
}

export function membersPanel(data) {
  const roles = '<select name="role" aria-label="批准后的角色"><option value="viewer">只读成员</option><option value="contributor">资料提交员</option><option value="reviewer">审核员</option></select>';
  return '<h2>成员与注册审批</h2><p class="muted">工作空间：' + esc(state.identity.workspace) + '。批准前请核实申请人的身份。</p>' +
    '<h3>待审批</h3>' + (data.pending.length ? data.pending.map(p =>
      '<form class="member-form"><input type="hidden" name="user_id" value="' + esc(p.user_id) + '"><strong>' + esc(p.user_id) + '</strong>' + roles +
      '<button name="action" value="approve" class="button primary">批准</button><button name="action" value="reject" class="button">拒绝</button></form>').join('') : '<p>暂无待审批申请。</p>') +
    '<h3>团队成员</h3>' + data.members.map(m => '<form class="member-form"><input type="hidden" name="user_id" value="' + esc(m.user_id) + '">' +
      '<strong>' + esc(m.user_id) + '</strong><span>' + esc(m.role) + ' · ' + (m.enabled ? '已启用' : '已停用') + '</span>' +
      (m.role !== 'admin' ? '<button name="action" value="' + (m.enabled ? 'disable' : 'enable') + '" class="button">' + (m.enabled ? '停用' : '启用') + '</button>' +
      (m.enabled ? '<button name="action" value="reset" class="button">签发重置码</button>' : '') : '<small>管理员找回密码由服务器命令处理</small>') + '</form>').join('');
}

export function checkPasswords(data) {
  if (data.get('password') !== data.get('confirm_password')) throw new Error('两次密码不一致，请重新输入。');
}
