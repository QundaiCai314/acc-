import { state } from './state.js';
import { esc, icon } from './ui.js';

export function loginPage() {
  const base = esc(state.client?.base || state.serverBase || 'http://127.0.0.1:8000');
  const workspace = esc(state.loginWorkspace || 'default');
  const mode = state.authMode || 'login';
  const signingIn = mode === 'login';
  return (
    '<div class="ds-login-stage">' +
    '<section class="ds-login-left" aria-label="登录表单区"><div class="ds-login-box">' +
    '<div class="ds-logo-circle" aria-hidden="true">' +
    icon('shield') +
    '</div>' +
    '<h1 class="ds-login-title">AI Disaster Commander</h1>' +
    '<div class="ds-mode-tabs" role="group" aria-label="登录与注册">' +
    '<button type="button" data-action="auth-mode" data-value="login" aria-pressed="' +
    signingIn +
    '">登录</button>' +
    '<button type="button" data-action="auth-mode" data-value="register" aria-pressed="' +
    (mode === 'register') +
    '">注册</button></div>' +
    (state.client
      ? '<div class="ds-session-card"><span>当前账号 · ' +
        esc(state.identity.user_id) +
        '</span><small>' +
        esc(state.identity.workspace) +
        ' / ' +
        esc(state.identity.role) +
        '</small>' +
        '<button type="button" class="ds-inline-link" data-action="account-settings">账号管理</button><button type="button" class="ds-inline-link" data-action="disconnect">退出登录</button></div>'
      : '') +
    '<p class="ds-terms" role="status">' +
    esc(
      state.authNotice ||
        (mode === 'register'
          ? '申请加入已有工作空间，由团队管理员核实后开通。'
          : mode === 'reset'
            ? '向管理员领取 30 分钟内有效的一次性重置码。'
            : ''),
    ) +
    '</p>' +
    '<form id="' +
    (signingIn
      ? 'login-form'
      : mode === 'register'
        ? 'register-account-form'
        : 'reset-password-form') +
    '" class="ds-form">' +
    '<label class="ds-field-label">账号<div class="ds-input-wrap">' +
    '<input class="ds-input" name="user_id" required maxlength="64" pattern="[a-zA-Z0-9_-]+" autocomplete="username" placeholder="英文字母、数字、下划线或短横线" autocapitalize="none" spellcheck="false"></div></label>' +
    (mode === 'reset'
      ? '<label class="ds-field-label">一次性重置码<input class="ds-input" name="reset_code" type="password" required maxlength="256" autocomplete="off"></label>'
      : '') +
    '<label class="ds-field-label" for="login-password">密码</label>' +
    '<div class="ds-input-wrap"><input id="login-password" class="ds-input with-Slot" name="password" type="password" required minlength="' +
    (signingIn ? 1 : 12) +
    '" maxlength="256" autocomplete="' +
    (signingIn ? 'current-password' : 'new-password') +
    '" aria-describedby="login-help">' +
    '<button type="button" class="ds-eye-btn" data-action="toggle-login-secret" data-target="login-password" aria-label="显示密码" aria-pressed="false">' +
    icon('scan') +
    '</button></div>' +
    (!signingIn
      ? '<label class="ds-field-label">确认密码<input class="ds-input" name="confirm_password" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label>'
      : '') +
    '<div class="ds-utility-row"><span>安全登录团队工作空间</span>' +
    '<button type="button" class="ds-forgot" data-action="login-help">忘记密码？</button></div>' +
    '<details class="ds-connection-options"' +
    (!signingIn ? ' open' : '') +
    '><summary>连接设置 · 工作空间</summary>' +
    '<label class="ds-field-label">工作空间<div class="ds-input-wrap"><input class="ds-input" name="workspace" required pattern="[a-zA-Z0-9_-]+" maxlength="64" autocomplete="off" value="' +
    workspace +
    '"></div></label>' +
    '<label class="ds-field-label">后端地址<div class="ds-input-wrap"><input class="ds-input" name="base" type="url" required autocomplete="off" value="' +
    base +
    '"></div></label></details>' +
    '<p id="login-help" class="ds-terms">' +
    (signingIn
      ? '会话有效期 8 小时，刷新后需重新登录。'
      : '密码需 12–256 个字符。请确认连接设置中的工作空间。') +
    '</p>' +
    '<button type="submit" class="ds-submit-btn">' +
    (signingIn ? '登录工作台' : mode === 'register' ? '提交注册申请' : '重置密码') +
    '</button></form>' +
    '<p id="login-error" class="ds-login-error" role="alert"></p>' +
    '<details class="ds-token-options"><summary>使用个人令牌 / 本机连接</summary>' +
    '<form id="connect-form" class="ds-form"><label class="ds-field-label">后端地址<div class="ds-input-wrap">' +
    '<input class="ds-input" name="base" type="url" required autocomplete="off" value="' +
    base +
    '"></div></label>' +
    '<label class="ds-field-label" for="login-token">个人访问令牌</label>' +
    '<div class="ds-input-wrap"><input id="login-token" class="ds-input with-Slot" name="token" type="password" autocomplete="off" aria-describedby="token-help">' +
    '<button type="button" class="ds-eye-btn" data-action="toggle-login-secret" data-target="login-token" aria-label="显示令牌" aria-pressed="false">' +
    icon('scan') +
    '</button></div>' +
    '<p id="token-help" class="ds-terms">团队令牌由管理员签发；本机 local 模式可留空。仅保存在当前页面。</p>' +
    '<button type="submit" class="ds-submit-btn">使用令牌连接</button></form></details>' +
    '<a class="ds-demo-link" href="#command">' +
    (state.client ? '返回已连接的工作台' : '查看工作台 →') +
    '</a>' +
    '<p class="ds-terms">登录后读取团队资料。未连接时不加载现场数据。</p>' +
    '</div></section>' +
    '<aside class="ds-login-right" data-slide="0" aria-label="主视觉展陈区">' +
    '<img class="ds-login-art" src="assets/login-hero-01.jpg" width="1086" height="1448" alt="浅绿色建筑模型与黄色空间控制点艺术图" fetchpriority="high">' +
    '<div class="ds-carousel-bars" role="group" aria-label="主视觉轮播">' +
    [0, 1, 2, 3]
      .map(
        (i) =>
          '<button type="button" class="ds-carousel-bar" data-action="login-slide" data-value="' +
          i +
          '" aria-pressed="' +
          (i === 0) +
          '" aria-label="主视觉 ' +
          (i + 1) +
          (i ? '（待补充）" disabled' : '"') +
          '></button>',
      )
      .join('') +
    '</div></aside></div>'
  );
}
