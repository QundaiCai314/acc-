import { state } from './state.js';
import { esc, icon } from './ui.js';

export function loginPage() {
  const base = esc(state.client?.base || state.serverBase || 'http://127.0.0.1:8000');
  const workspace = esc(state.loginWorkspace || 'default');
  return '<div class="ds-login-stage">' +
    '<section class="ds-login-left" aria-label="登录表单区"><div class="ds-login-box">' +
    '<div class="ds-logo-circle" aria-hidden="true">' + icon('shield') + '</div>' +
    '<h1 class="ds-login-title">AI Disaster Commander</h1>' +
    '<div class="ds-mode-tabs" role="group" aria-label="登录与注册">' +
    '<button type="button" aria-pressed="true">登录</button>' +
    '<button type="button" disabled title="账号由团队管理员创建">注册 · 未开放</button></div>' +
    (state.client ? '<div class="ds-session-card"><span>当前账号 · ' + esc(state.identity.user_id) +
      '</span><small>' + esc(state.identity.workspace) + ' / ' + esc(state.identity.role) + '</small>' +
      '<button type="button" class="ds-inline-link" data-action="disconnect">退出登录</button></div>' : '') +
    '<form id="login-form" class="ds-form">' +
    '<label class="ds-field-label">账号<div class="ds-input-wrap">' +
    '<input class="ds-input" name="user_id" required maxlength="64" autocomplete="username" placeholder="管理员分配的账号" autocapitalize="none" spellcheck="false"></div></label>' +
    '<label class="ds-field-label" for="login-password">密码</label>' +
    '<div class="ds-input-wrap"><input id="login-password" class="ds-input with-Slot" name="password" type="password" required maxlength="256" autocomplete="current-password" aria-describedby="login-help">' +
    '<button type="button" class="ds-eye-btn" data-action="toggle-login-secret" data-target="login-password" aria-label="显示密码" aria-pressed="false">' + icon('scan') + '</button></div>' +
    '<div class="ds-utility-row"><span>安全登录团队工作空间</span>' +
    '<button type="button" class="ds-forgot" data-action="login-help">忘记密码？</button></div>' +
    '<details class="ds-connection-options"><summary>连接设置 · 工作空间</summary>' +
    '<label class="ds-field-label">工作空间<div class="ds-input-wrap"><input class="ds-input" name="workspace" required maxlength="64" autocomplete="off" value="' + workspace + '"></div></label>' +
    '<label class="ds-field-label">后端地址<div class="ds-input-wrap"><input class="ds-input" name="base" type="url" required autocomplete="off" value="' + base + '"></div></label></details>' +
    '<p id="login-help" class="ds-terms">会话有效期 8 小时，刷新后需重新登录。</p>' +
    '<button type="submit" class="ds-submit-btn">登录工作台</button></form>' +
    '<p id="login-error" class="ds-login-error" role="alert"></p>' +
    '<details class="ds-token-options"><summary>使用个人令牌 / 本机连接</summary>' +
    '<form id="connect-form" class="ds-form"><label class="ds-field-label">后端地址<div class="ds-input-wrap">' +
    '<input class="ds-input" name="base" type="url" required autocomplete="off" value="' + base + '"></div></label>' +
    '<label class="ds-field-label" for="login-token">个人访问令牌</label>' +
    '<div class="ds-input-wrap"><input id="login-token" class="ds-input with-Slot" name="token" type="password" autocomplete="off" aria-describedby="token-help">' +
    '<button type="button" class="ds-eye-btn" data-action="toggle-login-secret" data-target="login-token" aria-label="显示令牌" aria-pressed="false">' + icon('scan') + '</button></div>' +
    '<p id="token-help" class="ds-terms">团队令牌由管理员签发；本机 local 模式可留空。仅保存在当前页面。</p>' +
    '<button type="submit" class="ds-submit-btn">使用令牌连接</button></form></details>' +
    '<div class="ds-divider"><span>第三方登录 · 暂未接入</span></div>' +
    '<div class="ds-social-stack"><button type="button" class="ds-social-btn" disabled>Continue with Google · 未接入</button>' +
    '<button type="button" class="ds-social-btn" disabled>Continue with Apple · 未接入</button></div>' +
    '<a class="ds-demo-link" href="#command">' + (state.client ? '返回已连接的工作台' : '进入离线演练 →') + '</a>' +
    '<p class="ds-terms">离线演练使用合成示例，不代表已登录团队。</p>' +
    '</div></section>' +
    '<aside class="ds-login-right" data-slide="0" aria-label="主视觉展陈区">' +
    '<img class="ds-login-art" src="assets/login-hero-01.jpg" width="1086" height="1448" alt="浅绿色建筑模型与黄色空间控制点艺术图" fetchpriority="high">' +
    '<div class="ds-carousel-bars" role="group" aria-label="主视觉轮播">' +
    [0, 1, 2, 3].map(i => '<button type="button" class="ds-carousel-bar" data-action="login-slide" data-value="' + i +
      '" aria-pressed="' + (i === 0) + '" aria-label="主视觉 ' + (i + 1) + (i ? '（待补充）" disabled' : '"') + '></button>').join('') +
    '</div></aside></div>';
}
