// Credentials live only in memory, never in browser storage or URLs.
export class Client {
  constructor(base, token = '') {
    const u = new URL(base);
    if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password || u.search || u.hash)
      throw new Error('请输入不含账号、查询参数的 HTTP(S) 服务地址。');
    if (u.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(u.hostname))
      throw new Error('远程团队服务请使用 HTTPS，避免令牌明文传输。');
    this.base = u.href.replace(/\/$/, '');
    this.token = token;
    this.blobs = new Map();
    this.controllers = new Set();
    this.disposed = false;
  }
  async request(path, body, extra = {}) {
    if (this.disposed) throw new Error('连接已关闭，请重新登录。');
    const controller = new AbortController();
    this.controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const response = await fetch(this.base + path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: {
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
          ...(this.token ? { Authorization: 'Bearer ' + this.token } : {}),
          ...extra,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        cache: 'no-store',
        credentials: 'omit',
        redirect: 'error',
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const authMessages = {
          'Account already exists; contact the workspace administrator': '此账号已存在，请直接登录或联系管理员。',
          'Workspace is not accepting registration; contact its administrator': '此工作空间尚未开放注册，请向管理员核对工作空间名称。',
          'Registration is already awaiting approval': '此账号已有待审批申请，请联系管理员处理。',
          'Registration is no longer pending': '此申请已被处理，请刷新成员列表。',
          'Invalid or expired reset code': '重置码不正确或已过期，请向管理员重新领取。',
          'Current password is incorrect': '当前密码不正确，请重新输入。',
          'Manage administrator credentials using the server command': '管理员凭据由服务器账号管理命令重置。',
          'Invalid account fields; new passwords require 12 to 256 characters': '请核对账号、工作空间与密码。新密码需 12–256 个字符。',
          'Provide a valid account, workspace and password of at least 12 characters': '账号和工作空间只能包含英文字母、数字、下划线或短横线；密码需 12–256 个字符。',
          'Registration requires team mode': '请将后端切换到 team 模式后注册。',
          'Account management requires team mode': '此功能需要 team 模式，请连接团队后端。',
        };
        const messages = {
          401: path === '/auth/login' ? '账号、密码或工作空间不正确，请核对后重试。' : '登录已过期或身份已撤销，请重新登录。',
          403: '当前账号没有此操作权限。',
          409: path === '/auth/login' ? '当前后端为本机模式，请使用下方本机连接入口；账号登录需启用 team 模式。' : '记录已被其他人处理，或不在有效期内。请刷新后复核，勿重复提交。',
          413: '资料超过服务接收上限，请缩小文件后重试。',
          429: '请求过于频繁，请稍后再试。',
          502: '外部模型或搜索服务返回异常，请检查服务配置后重试。',
          503: '服务未配置或暂时不可用，请检查后端配置。',
        };
        const detail =
          typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || '');
        const error = new Error(
          (authMessages[data.detail] || messages[response.status] || '请求未完成，请核对输入。') +
            ' [' +
            response.status +
            '] ' +
            (authMessages[data.detail] ? '' : detail.slice(0, 900)),
        );
        error.status = response.status;
        if (response.status === 401 && path !== '/auth/login') this.onUnauthorized?.();
        throw error;
      }
      const data = await (path.endsWith('/content') ? response.blob() : response.json());
      if (this.disposed) throw new Error('连接已关闭，请重新登录。');
      return data;
    } catch (e) {
      if (e.name === 'AbortError')
        throw new Error('请求超时，服务端可能仍在处理。请先刷新查看结果，再决定是否重试。');
      if (e instanceof TypeError)
        throw new Error('无法连接后端，请检查服务地址、网络与 CORS 配置，然后重试。');
      throw e;
    } finally {
      clearTimeout(timeout);
      this.controllers.delete(controller);
    }
  }
  async list(path, key) {
    const rows = [];
    let offset = 0;
    do {
      const page = await this.request(path + '?limit=200&offset=' + offset);
      rows.push(...page[key]);
      offset = page.next_offset;
    } while (offset != null);
    return rows;
  }
  async image(id) {
    if (!this.blobs.has(id))
      this.blobs.set(
        id,
        this.request('/spatial/images/' + encodeURIComponent(id) + '/content')
          .then((blob) => URL.createObjectURL(blob))
          .catch((e) => {
            this.blobs.delete(id);
            throw e;
          }),
      );
    return this.blobs.get(id);
  }
  dispose() {
    this.disposed = true;
    clearTimeout(this.expiryTimer);
    this.onUnauthorized = null;
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
    for (const p of this.blobs.values()) p.then(URL.revokeObjectURL).catch(() => {});
    this.blobs.clear();
    this.token = '';
  }
}
