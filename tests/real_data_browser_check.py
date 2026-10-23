"""Real-only UI contract checks against the disposable test server, never user data."""
import base64
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8080/#command')
        page.get_by_role('button', name='连接设置').click()
        page.locator('#connect-form [name=base]').fill('http://127.0.0.1:8002')
        page.locator('#connect-form [name=token]').fill('frontend-test-isolated')
        page.get_by_role('button', name='连接并读取现场').click()
        expect(page.locator('#dialog')).not_to_be_visible(timeout=15000)
        page.evaluate("location.hash='import'")
        form = page.locator('#create-site-form')
        for name, value in [('title', '隔离测试：未知位置'), ('entity_id', 'unlocated'),
                            ('entity_name', '未定位对象'), ('source', '测试夹具；不是真实测绘资料')]:
            form.locator('[name='+name+']').fill(value)
        form.locator('[name=latitude]').fill('30')
        form.get_by_role('button', name='建立真实现场').click()
        expect(page.locator('#notice')).to_contain_text('经纬度需同时填写')
        form.locator('[name=latitude]').fill('')
        form.get_by_role('button', name='建立真实现场').click()
        expect(page.locator('#notice')).to_have_text('操作完成。', timeout=15000)
        assert page.evaluate("async () => (await import('./state.js')).state.dataset.snapshot.entities[0].coordinates === null")
        expect(page.locator('#image-form [name=captured_at]')).to_have_value('')
        # Intentional synthetic contract image lives only in the disposable database.
        png = page.evaluate("() => {const c=document.createElement('canvas');c.width=10;c.height=10;return c.toDataURL().split(',')[1]}")
        page.locator('#image-form input[type=file]').set_input_files({
            'name': 'contract-only.png', 'mimeType': 'image/png', 'buffer': base64.b64decode(png)})
        page.locator('#image-form [name=captured_at]').fill('2026-01-01T12:00')
        page.locator('#image-form [name=captured_on]').fill('2026-01-01')
        page.locator('#image-form [name=source]').fill('测试专用合成图，非现场照片')
        page.get_by_role('button', name='上传至当前现场').click()
        expect(page.locator('#notice')).to_contain_text('请填写其中一项')
        page.locator('#image-form [name=captured_at]').fill('')
        page.get_by_role('button', name='上传至当前现场').click()
        expect(page.locator('#notice')).to_have_text('操作完成。', timeout=15000)
        assert page.evaluate("async () => !(await import('./state.js')).state.images[0].camera_pose")
        assert page.evaluate("async () => {const i=(await import('./state.js')).state.images[0];return i.captured_at === null && i.captured_on === '2026-01-01'}")
        assert page.evaluate("""async () => {
            const {captureWithinWindow}=await import('./capture-time.js');
            const image={captured_on:'2026-01-01'};
            return captureWithinWindow(image,'2026-01-02T12:00:00Z',50)
              && !captureWithinWindow(image,'2026-01-02T12:00:00Z',49)
              && !captureWithinWindow(image,'2026-01-02T11:59:59Z',50);
        }""")
        checks = page.evaluate("""async () => {
            const {inputTemplate,validateRealDataset,validateRealImage}=await import('./intake.js');
            const rejected=[];
            for (const fn of [() => validateRealDataset({coordinate_basis:'exercise'}),
                () => validateRealImage({evidence_basis:'exercise'}),
                () => validateRealImage({evidence_basis:'field_image',camera_pose:{position_basis:'exercise'}})]) {
                try {fn();rejected.push(false)} catch {rejected.push(true)}
            }
            return {rejected, template:inputTemplate('dataset'), road:inputTemplate('networks')};
        }""")
        assert all(checks['rejected'])
        assert checks['template']['entities'][0]['coordinates'] is None
        assert checks['road']['valid_from'] == '' and checks['road']['edges'][0]['length_m'] is None
        page.evaluate("location.hash='command'")
        page.get_by_role('button', name='数据', exact=True).click()
        panel = page.locator('[data-window=data]')
        expect(panel).to_contain_text('测试夹具；不是真实测绘资料')
        expect(panel).to_contain_text('待审核有效路网')
        expect(panel.locator('.data-metrics strong').first).to_have_text('0')
        output = Path('data/frontend-check')
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / 'real-data-unlocated.png'))
        panel.locator('[data-action=minimize-window]').click()
        expect(panel).to_have_count(0)
        page.locator('[data-action=restore-window][data-window-id=data]').click()
        expect(panel).to_be_visible()
        page.get_by_role('button', name='数据', exact=True).click()
        page.get_by_role('button', name='问答', exact=True).click()
        page.locator('#ask-form [name=kind]').select_option('references/search')
        page.locator('#question').fill('验证断线不返回模拟背景')
        page.get_by_role('button', name='提交问题').click()
        expect(page.locator('.references')).to_contain_text('未核实背景', timeout=15000)
        # Deliberately fail a replacement request. Earlier output must disappear.
        page.route('http://127.0.0.1:8002/**', lambda route: route.abort())
        page.get_by_role('button', name='提交问题').click()
        expect(page.locator('#notice')).to_contain_text('无法连接后端')
        expect(page.locator('.references')).to_have_count(0)
        expect(page.locator('.topbar [data-connection-state]')).to_contain_text('连接中断')
        page.get_by_role('button', name='刷新', exact=True).click()
        expect(page.locator('.topbar [data-connection-state]')).to_contain_text('同步失败')
        assert page.evaluate("async () => {const s=(await import('./state.js')).state;return s.dataset && s.images.length === 1 && !s.answer && !s.route && !s.references}")
        page.unroute('http://127.0.0.1:8002/**')
        page.get_by_role('button', name='刷新', exact=True).click()
        expect(page.locator('.topbar [data-connection-state]')).to_have_text('后端已连接')
        page.get_by_role('button', name='问答', exact=True).click()
        page.route('http://127.0.0.1:8002/**', lambda route: route.abort())
        page.locator('#quick-question-text').fill('查证这个现场')
        page.get_by_role('button', name='打开证据问答', exact=True).click()
        expect(page.locator('#notice')).to_contain_text('无法连接后端')
        expect(page.locator('#question')).to_have_value('查证这个现场')
        expect(page.get_by_role('button', name='提交问题')).to_be_enabled()
        assert not errors, errors
        browser.close()
    print('PASS: sourced-site form, unlocated media, blank templates, exercise rejection, source window, disconnected/stale/reconnected states; no real provider calls.')


if __name__ == '__main__':
    main()
