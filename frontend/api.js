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
  }
  async request(path, body, extra = {}) {
    const controller = new AbortController();
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
        const messages = {
          401: '身份验证失效，请重新连接并填写有效个人令牌。',
          403: '当前账号没有此操作权限。',
          409: '记录已被其他人处理，或不在有效期内。请刷新后复核，勿重复提交。',
          413: '资料超过服务接收上限，请缩小文件后重试。',
          429: '请求过于频繁，请稍后再试。',
          502: '外部模型或搜索服务返回异常，请检查服务配置后重试。',
          503: '服务未配置或暂时不可用，请检查后端配置。',
        };
        const detail =
          typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || '');
        throw new Error(
          (messages[response.status] || '请求未完成，请核对输入。') +
            ' [' +
            response.status +
            '] ' +
            detail.slice(0, 900),
        );
      }
      return path.endsWith('/content') ? response.blob() : response.json();
    } catch (e) {
      if (e.name === 'AbortError')
        throw new Error('请求超时，服务端可能仍在处理。请先刷新查看结果，再决定是否重试。');
      if (e instanceof TypeError)
        throw new Error('无法连接后端，请检查服务地址、网络与 CORS 配置，然后重试。');
      throw e;
    } finally {
      clearTimeout(timeout);
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
    for (const p of this.blobs.values()) p.then(URL.revokeObjectURL).catch(() => {});
    this.blobs.clear();
    this.token = '';
  }
}
