// Surface module failures instead of leaving a blank page or an inert initial skeleton.
import('./app.js').catch(() => {
  const root = document.querySelector('#app');
  const message = document.createElement('p');
  message.setAttribute('role', 'alert');
  message.textContent = '工作台加载失败，请检查本地服务与网络后重试。';
  const retry = document.createElement('button');
  retry.textContent = '重新加载';
  retry.addEventListener('click', () => location.reload());
  root.replaceChildren(message, retry);
});
