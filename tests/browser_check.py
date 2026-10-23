"""Optional Playwright integration check; requires the disposable fixture server.

python tests/browser_check.py --url http://127.0.0.1:8080 --api http://127.0.0.1:8002
The browser must be installed (default channel: chrome). No paid model calls.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from ui_fixture import fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--api', default='http://127.0.0.1:8002')
    parser.add_argument('--channel', default='chrome')
    args = parser.parse_args()
    output = Path('data/frontend-check')
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=args.channel)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.wait_for_load_state('networkidle')
        expect(page.locator('.ds-login-title')).to_contain_text('AI Disaster Commander')
        page.get_by_role('button', name='注册').click()
        expect(page.locator('#register-account-form')).to_be_visible()
        expect(page.get_by_role('button', name='提交注册申请')).to_be_visible()
        page.get_by_role('button', name='登录').click()
        page.get_by_role('link', name='查看工作台').click()
        expect(page.locator('.workspace-onboarding')).to_be_visible()
        assert page.evaluate("async () => {const {state,canWrite,canReview}=await import('./state.js');return !state.dataset && !state.images.length && !state.annotations.length && !state.artifacts.length && !canWrite() && !canReview()}")
        assert not any('/demo' in r['name'] for r in page.evaluate('performance.getEntriesByType("resource").map(r=>({name:r.name}))'))
        page.screenshot(path=str(output / 'real-first-empty-desktop.png'))
        demo = fixture(page)  # Test-only generated data; never written to a user backend.
        for width in (320, 768, 1024, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            for route in ('command', 'import', 'analysis', 'review', 'registration', 'plans', 'reason', 'field'):
                page.goto(args.url + '/#' + route)
                page.wait_for_load_state('networkidle')
                assert page.locator('h1').count() == 1, route
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, route)
            page.goto(args.url + '/#command')
            page.screenshot(path=str(output / f'real-first-empty-{width}.png'))
        expect(page.locator('.geo-label')).to_have_count(0)
        page.get_by_role('button', name='对象', exact=True).click()
        expect(page.get_by_role('button', name='检索已审核障碍物')).to_be_disabled()
        page.get_by_role('button', name='对象', exact=True).click()

        def connect(token):
            page.get_by_role('button', name='连接设置').click()
            page.locator('#connect-form [name=base]').fill(args.api)
            page.locator('#connect-form [name=token]').fill(token)
            page.get_by_role('button', name='连接并读取现场').click()
            expect(page.locator('#dialog')).not_to_be_visible(timeout=15000)
            expect(page.locator('.topbar')).to_contain_text('后端已连接')

        # The restored full-page login must reject invalid tokens without entering a team workspace.
        page.goto(args.url + '/#login')
        page.locator('.ds-token-options > summary').click()
        page.locator('#connect-form [name=base]').fill(args.api)
        page.locator('#login-token').fill('invalid-login-token')
        page.get_by_role('button', name='显示令牌', exact=True).click()
        expect(page.locator('#login-token')).to_have_value('invalid-login-token')
        expect(page.locator('#login-token')).to_have_attribute('type', 'text')
        page.get_by_role('button', name='隐藏令牌', exact=True).click()
        page.get_by_role('button', name='使用令牌连接', exact=True).click()
        expect(page.locator('#login-error')).to_contain_text('401', timeout=15000)
        assert page.evaluate("async () => (await import('./state.js')).state.client === null")
        expect(page.locator('#login-token')).to_have_value('invalid-login-token')
        page.locator('#login-token').fill('frontend-test-admin')
        page.get_by_role('button', name='使用令牌连接', exact=True).click()
        expect(page.locator('.topbar')).to_contain_text('后端已连接', timeout=15000)
        assert page.evaluate('!localStorage.length && !sessionStorage.length')
        expect(page.locator('.contextbar')).to_contain_text('尚未选择现场')
        page.goto(args.url + '/#import')
        dataset_file = output / 'map.json'
        demo['dataset']['snapshot']['coordinate_basis'] = 'measured'  # Contract fixture only, not a real survey.
        dataset_file.write_text(json.dumps(demo['dataset']['snapshot'], ensure_ascii=False), encoding='utf-8')
        page.locator('.intake-json > summary').click()
        page.locator('#dataset-form input[type=file]').set_input_files(dataset_file)
        page.get_by_role('button', name='建立新现场').click()
        expect(page.locator('.contextbar')).to_contain_text('北城街区', timeout=15000)
        # PNG is created in the browser; no graphics library or real photos required.
        png = page.evaluate("""() => {const c=document.createElement('canvas');c.width=640;c.height=400;
            const x=c.getContext('2d');x.fillStyle='#586a64';x.fillRect(0,0,640,400);
            x.fillStyle='#203430';x.fillRect(200,100,200,250);return c.toDataURL().split(',')[1];}""")
        import base64
        page.locator('#image-form input[type=file]').set_input_files({'name': 'synthetic.png', 'mimeType': 'image/png', 'buffer': base64.b64decode(png)})
        page.locator('#image-form [name=captured_at]').fill(__import__('datetime').datetime.now().strftime('%Y-%m-%dT%H:%M'))
        page.locator('#image-form [name=source]').fill('浏览器合成图，非现场照片')
        page.locator('.camera-fields > summary').click()
        page.locator('[name=camera_enabled]').check()
        for name, value in [('camera_lat','31.23'),('camera_lon','121.47'),('camera_heading','315'),('camera_fov','65'),('camera_alt','1.8'),('camera_pitch','0'),('camera_vfov','45'),('camera_source','合成测试位姿')]:
            page.locator('[name='+name+']').fill(value)
        page.get_by_role('button', name='上传至当前现场').click()
        expect(page.locator('#notice')).to_have_text('操作完成。', timeout=15000)
        page.goto(args.url + '/#analysis')
        page.get_by_role('button', name='请求 AI 分析').click()
        expect(page.locator('#review-form [name=entity_id]')).to_have_value('east', timeout=15000)
        expect(page.locator('.review-editor .panel-heading')).to_contain_text('候选待审')
        expect(page.locator('.evidence-photo img')).to_have_attribute('src', __import__('re').compile('blob:'))
        page.get_by_role('button', name='领取审核', exact=True).click()
        expect(page.locator('.lease-panel')).to_contain_text('admin 占用至')
        page.get_by_role('button', name='刷新', exact=True).click()
        expect(page.locator('.lease-panel')).to_contain_text('admin 占用至')
        page.get_by_role('button', name='释放', exact=True).click()
        expect(page.locator('.lease-panel')).to_contain_text('当前未占用')
        page.locator('[name=description]').fill('人工修正：仅确认可见散落构件。')
        page.locator('[name=note]').fill('对照合成图片核验')
        page.get_by_role('button', name='批准 / 修正').click()
        expect(page.locator('.review-editor .panel-heading')).to_contain_text('已审核', timeout=15000)
        page.goto(args.url + '/#command')
        if not page.locator('[data-window=objects]').count():
            page.get_by_role('button', name='对象', exact=True).click()
        page.get_by_role('button', name='检索已审核障碍物').click()
        expect(page.locator('.answer')).to_contain_text('人工修正：', timeout=15000)
        page.locator('#question').fill('A 楼 100 米内哪些入口有障碍物？')
        page.get_by_role('button', name='提交问题').click()
        expect(page.locator('.answer')).to_contain_text('运行', timeout=15000)
        expect(page.locator('.inline-citation')).not_to_have_count(0)
        page.locator('.inline-citation').first.click()
        expect(page.locator('.citation.active')).to_be_visible()
        pose = page.evaluate("async () => (await import('./state.js')).state.images[0].camera_pose")
        assert pose['heading_deg'] == 315
        page.locator('#ask-form [name=kind]').select_option('references/search')
        page.locator('#question').fill('USGS 地震准备')
        page.get_by_role('button', name='提交问题').click()
        expect(page.locator('.references')).to_contain_text('未核实背景', timeout=15000)

        for route, kind in [('plans', 'road_network'), ('registration', 'registration'), ('reason', 'relation_set')]:
            page.goto(args.url + '/#' + route)
            artifact = next(a for a in demo['artifacts'] if a['artifact_type'] == kind)
            path = output / (kind + '.json')
            path.write_text(json.dumps(artifact['snapshot']), encoding='utf-8')
            page.locator('#artifact-form input[type=file]').set_input_files(path)
            page.get_by_role('button', name='导入待审快照').click()
            expect(page.locator('#notice')).to_have_text('操作完成。', timeout=15000)
            if kind != 'registration':
                page.locator('.artifact-detail > summary').click()
            page.locator('.artifact-review-form [name=note]').fill('浏览器核验：合成工件')
            page.get_by_role('button', name='批准快照').click()
            expect(page.locator('#notice')).to_have_text('操作完成。', timeout=15000)
        page.goto(args.url + '/#plans')
        page.locator('[name=start_entity_id]').select_option('west')
        page.locator('[name=end_entity_id]').select_option('east')
        page.get_by_role('button', name='计算路径').click()
        expect(page.locator('.route-result')).to_contain_text('350', timeout=15000)
        page.locator('#route-form [name=basis]').select_option('mapped_topology')
        page.get_by_role('button', name='计算路径').click()
        expect(page.locator('.route-result')).to_contain_text('仅地图拓扑', timeout=15000)
        assert page.evaluate("async () => (await import('./state.js')).state.route.basis") == 'mapped_topology'
        page.goto(args.url + '/#reason')
        page.get_by_role('button', name='增加条件', exact=False).click()
        rows = page.locator('.condition-row')
        rows.nth(1).locator('[name=relation]').select_option('part_of')
        # The workspace retains query drafts, including an earlier empty snapshot selection.
        page.locator('#reason-form [name=relation_set_id]').select_option(index=1)
        page.get_by_role('button', name='执行联合查询').click()
        expect(page.locator('.answer')).to_contain_text('东入口', timeout=15000)
        assert page.locator('.condition-row').count() == 2, 'Keep submitted query conditions visible'
        page.screenshot(path=str(output / 'reason-connected.png'), full_page=True)

        # Simulate another reviewer submitting first; retain the user's note on 409.
        page.goto(args.url + '/#field')
        page.locator('#observation-form [name=description]').fill('并发审核测试候选')
        page.locator('#observation-form [name=source_note]').fill('测试录入')
        page.get_by_role('button', name='提交待审观察').click()
        expect(page.locator('#notice')).to_have_text('操作完成。', timeout=15000)
        page.goto(args.url + '/#review')
        page.locator('.review-item').last.click()
        annotation_id = page.evaluate("async () => (await import('./state.js')).state.annotationId")
        competitor = page.request.post(args.api + '/spatial/annotations/' + annotation_id + '/review',
            headers={'Authorization': 'Bearer frontend-test-admin'},
            data={'reviewer': 'ignored', 'action': 'approve', 'note': '另一审核员先提交'})
        assert competitor.status == 201
        page.locator('#review-form [name=note]').fill('我的审核意见应保留')
        page.get_by_role('button', name='批准 / 修正').click()
        expect(page.locator('#notice')).to_contain_text('[409]', timeout=15000)
        expect(page.locator('#review-form [name=note]')).to_have_value('我的审核意见应保留')
        page.get_by_role('button', name='刷新', exact=True).click()
        expect(page.locator('.review-editor .panel-heading')).to_contain_text('已审核', timeout=15000)

        # Team permissions and workspace isolation are checked against the real middleware.
        connect('frontend-test-viewer')
        page.locator('.primary-modes a[href="#command"]').click()
        page.get_by_role('button', name='切换现场 ↓').click()
        page.get_by_role('button', name='打开现场', exact=True).click()
        expect(page.locator('#dialog')).not_to_be_visible()
        page.locator('.primary-modes a[href="#analysis"]').click()
        page.locator('.workflow-tabs a[href="#review"]').click()
        expect(page.get_by_role('button', name='撤回批准', exact=True)).to_be_disabled()
        page.goto(args.url + '/#import')
        expect(page.get_by_role('button', name='建立真实现场')).to_be_disabled()
        connect('frontend-test-isolated')
        expect(page.locator('.contextbar')).to_contain_text('尚未选择现场')
        assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0'), 'No credentials in storage'
        # Escape server-controlled names rather than executing their markup.
        page.evaluate("async () => {const {state}=await import('./state.js');state.dataset={id:'test',snapshot:{title:'<img src=x onerror=alert(1)>',entities:[]}};location.hash='field';}")
        expect(page.locator('.contextbar strong')).to_have_text('<img src=x onerror=alert(1)>')
        assert page.locator('.contextbar img').count() == 0
        page.goto(args.url + '/#login')
        expect(page.get_by_role('link', name='返回已连接的工作台')).to_be_visible()
        expect(page.locator('#login-token')).to_have_value('')
        page.reload()
        expect(page.get_by_role('link', name='查看工作台')).to_be_visible()
        expect(page.locator('#login-token')).to_have_value('')
        assert page.evaluate("async () => (await import('./state.js')).state.client === null")
        # Password sessions use the same actual backend and must revoke on logout.
        def password_login(password='frontend-test-password'):
            page.locator('.ds-connection-options > summary').click()
            page.locator('#login-form [name=base]').fill(args.api)
            page.locator('#login-form [name=workspace]').fill('browser-test')
            page.locator('#login-form [name=user_id]').fill('admin')
            page.locator('#login-password').fill(password)
            page.get_by_role('button', name='登录工作台', exact=True).click()

        password_login('wrong-password')
        expect(page.locator('#login-error')).to_contain_text('401', timeout=15000)
        expect(page.locator('#login-form [name=user_id]')).to_have_value('admin')
        page.get_by_role('button', name='显示密码', exact=True).click()
        expect(page.locator('#login-password')).to_have_attribute('type', 'text')
        page.get_by_role('button', name='隐藏密码', exact=True).click()
        page.locator('#login-password').fill('frontend-test-password')
        page.get_by_role('button', name='登录工作台', exact=True).click()
        expect(page.locator('.topbar')).to_contain_text('后端已连接', timeout=15000)
        token = page.evaluate("async () => (await import('./state.js')).state.client.token")
        page.get_by_role('button', name='连接设置').click()
        page.get_by_role('button', name='退出登录', exact=True).click()
        expect(page.locator('#login-password')).to_be_visible()
        assert page.request.get(args.api + '/auth/me', headers={'Authorization': 'Bearer '+token}).status == 401
        assert page.evaluate("async () => {const s=(await import('./state.js')).state;return !s.client && !s.answer && !s.datasets.length && !s.dataset && !s.images.length && !s.annotations.length && !s.artifacts.length && s.identity.role === ''}")
        password_login()
        expect(page.locator('.topbar')).to_contain_text('后端已连接', timeout=15000)
        token = page.evaluate("async () => (await import('./state.js')).state.client.token")
        assert page.request.post(args.api+'/auth/logout', headers={'Authorization':'Bearer '+token}, data={}).ok
        page.get_by_role('button', name='刷新', exact=True).click()
        expect(page.locator('#login-password')).to_be_visible(timeout=15000)
        assert page.evaluate("async () => {const s=(await import('./state.js')).state;return !s.client && !s.answer && !s.datasets.length && !s.dataset && !s.images.length && !s.annotations.length && !s.artifacts.length && s.identity.role === ''}")
        assert page.evaluate('!localStorage.length && !sessionStorage.length')
        assert not errors, errors
        browser.close()
    print('PASS: login rejection/success/refresh; 32 responsive page checks; empty-first/no local success; real team API upload, analysis fixture, review, query, artifacts, relation reasoning, permissions, isolation, escaping.')
    print('Screenshots: data/frontend-check/')


if __name__ == '__main__':
    main()
