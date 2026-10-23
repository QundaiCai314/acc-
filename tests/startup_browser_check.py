"""Real browser fault injection: no vendor required for sign-in; actionable load failures."""
from playwright.sync_api import sync_playwright, expect


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='chrome')
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    requested = []
    page.on('request', lambda request: requested.append(request.url))
    page.route('**/vendor/**', lambda route: route.abort())
    page.goto('http://127.0.0.1:8080/')
    page.get_by_role('button', name='注册', exact=True).click()
    expect(page.get_by_role('button', name='提交注册申请')).to_be_visible()
    assert not any('/vendor/' in url and url.endswith(('.js', '.mjs')) for url in requested), requested
    page.goto('http://127.0.0.1:8080/#command')
    expect(page.locator('#basemap-status')).to_contain_text('地图组件加载失败')
    expect(page.locator('#gis-slot svg')).to_be_visible()
    # Explicit UI-only fixture: verifies failure behavior, not real registration accuracy.
    page.evaluate('''async () => {
        const {state} = await import('./state.js');
        const {sceneControls, mountScene} = await import('./scene.js');
        const reg = {id:'startup-test', snapshot:{target_frame:'local',
            control_points:[{label:'fixture',local_m:[0,0,0]}],check_points:[]}};
        state.artifacts = [reg];
        const host = document.createElement('div');
        host.innerHTML = sceneControls(reg);
        document.body.append(host);
        mountScene();
    }''')
    expect(page.locator('#scene-slot')).to_contain_text('三维组件加载失败')
    expect(page.locator('.control-plan')).to_be_visible()
    context.close()

    context = browser.new_context()
    page = context.new_page()
    page.route('**/app.js', lambda route: route.abort())
    page.goto('http://127.0.0.1:8080/')
    expect(page.get_by_role('alert')).to_contain_text('工作台加载失败')
    expect(page.get_by_role('button', name='重新加载')).to_be_visible()
    page.unroute('**/app.js')
    page.get_by_role('button', name='重新加载').click()
    expect(page.get_by_role('button', name='注册', exact=True)).to_be_visible()
    context.close()
    browser.close()
print('PASS: login independent of GIS/3D bundles, map/3D fallback, bootstrap failure and retry.')
